from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from types import SimpleNamespace

from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from accounts.models import AccessGroup, User
from assets.models import Equipment, EquipmentCategory
from customers.models import Customer
from logistics.models import TransportTask, Vehicle
from logistics.services import task_items
from .documents import snapshot_for, render_document_pdf, snapshot_hash
from .freight import estimate_period_freight
from .models import RentalQuote, RentalItem, RentalInspection, RentalDocument
from .services import availability_reason


class ItemPeriodFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        group = AccessGroup.objects.create(name="Operações por item", permissions=["*"])
        cls.user = User.objects.create_user("periods@example.invalid", "test", full_name="Operador", access_group=group)
        cls.customer = Customer.objects.create(person_type="PF", name="Cliente de teste", document="12345678909", phone="19999999999")
        category = EquipmentCategory.objects.create(name="Teste de períodos")
        cls.assets = [Equipment.objects.create(category=category, name=f"Item {i}", internal_code=f"PER-{i}", serial_number=f"PER-{i}", daily_rate=100, estimated_weight_kg=100) for i in range(3)]
        cls.today = timezone.localdate()

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def create_quote(self, transport=False, same_start=False):
        response = self.client.post('/api/rental-quotes/', {
            'customer': self.customer.pk, 'start_date': str(self.today), 'end_date': str(self.today+timedelta(days=8)),
            'conditions': 'Condições de teste', 'status': 'APPROVED',
            'delivery_transport_required': transport, 'return_transport_required': transport,
            'delivery_address': 'Rua de teste, 10', 'return_address': 'Rua de teste, 10',
            'items': [
                {'equipment_id': self.assets[0].pk, 'daily_rate': '100', 'start_date': str(self.today), 'end_date': str(self.today+timedelta(days=1))},
                {'equipment_id': self.assets[1].pk, 'daily_rate': '150', 'start_date': str(self.today if same_start else self.today+timedelta(days=2)), 'end_date': str(self.today+timedelta(days=4))},
            ],
        },format='json')
        self.assertEqual(response.status_code,201,response.data)
        return RentalQuote.objects.get(pk=response.data['id'])

    def action(self, quote, action, ids=None, expected=200, **payload):
        if ids is not None: payload['equipment_ids'] = ids
        response=self.client.post(f'/api/rental-quotes/{quote.pk}/{action}/',payload,format='json')
        self.assertEqual(response.status_code,expected,response.data)
        quote.refresh_from_db()
        return response

    def inspect(self, quote, asset, kind='PRE_RENTAL', result='APPROVED', condition='GOOD'):
        inspection=RentalInspection.objects.get(quote=quote,equipment=asset,inspection_type=kind)
        response=self.client.patch(f'/api/rental-inspections/{inspection.pk}/',{
            'checklist':[{**entry,'status':'OK'} for entry in inspection.checklist], 'result':result, 'condition':condition,
        },format='json')
        self.assertEqual(response.status_code,200,response.data)

    def test_billing_and_availability_use_each_item_period(self):
        quote=self.create_quote()
        self.assertEqual((quote.start_date,quote.end_date),(self.today,self.today+timedelta(days=4)))
        self.assertEqual(quote.subtotal,Decimal('650'))
        first=quote.items.get(equipment=self.assets[0]); self.assertEqual(first.quantity_days,2)
        self.assertIsNone(availability_reason(self.assets[0],self.today+timedelta(days=2),self.today+timedelta(days=3)))
        self.assertIsNotNone(availability_reason(self.assets[0],self.today,self.today))

    def test_partial_flow_keeps_other_items_and_closes_only_after_all(self):
        quote=self.create_quote()
        first,second=self.assets[:2]
        self.inspect(quote,first)
        self.action(quote,'deliver',[first.pk])
        self.assertEqual(quote.status,'ACTIVE')
        self.assertEqual(quote.items.get(equipment=second).stage,'PENDING')
        # The remaining pre-inspection is editable while the quote is active.
        self.inspect(quote,second)
        self.action(quote,'return',[first.pk])
        self.assertEqual(quote.status,'ACTIVE'); self.assertIsNone(quote.returned_at)
        self.assertEqual(quote.inspections.filter(inspection_type='RETURN').count(),1)
        self.action(quote,'finalize-return',[first.pk],expected=400)
        self.inspect(quote,first,'RETURN')
        self.action(quote,'finalize-return',[first.pk])
        first.refresh_from_db(); self.assertEqual(first.status,'AVAILABLE')
        self.assertEqual(quote.status,'ACTIVE')
        self.action(quote,'deliver',[second.pk])
        self.action(quote,'return',[second.pk]); self.assertEqual(quote.status,'RETURNED')
        self.inspect(quote,second,'RETURN')
        self.action(quote,'finalize-return',[second.pk]); self.assertEqual(quote.status,'COMPLETED')

    def test_selection_rejects_wrong_quote_duplicates_wrong_stage_and_early_return(self):
        quote=self.create_quote(); first=self.assets[0]
        for ids in ([],[first.pk,first.pk],[self.assets[2].pk]):
            self.action(quote,'deliver',ids,expected=400)
        self.action(quote,'return',[first.pk],expected=400)
        self.inspect(quote,first); self.action(quote,'deliver',[first.pk])
        self.action(quote,'deliver',[first.pk],expected=400)
        self.action(quote,'return',[first.pk],expected=400,returned_at=(timezone.now()-timedelta(days=1)).isoformat())
        self.assertEqual(quote.items.get(equipment=first).stage,'DELIVERED')

    def test_partial_document_has_only_moved_items_and_immutable_periods(self):
        quote=self.create_quote(); first=self.assets[0]
        self.inspect(quote,first); self.action(quote,'deliver',[first.pk]); self.action(quote,'return',[first.pk])
        response=self.client.post(f'/api/rental-quotes/{quote.pk}/documents/',{'kind':'RETURN'},format='json')
        self.assertEqual(response.status_code,201,response.data)
        document=RentalDocument.objects.get(pk=response.data['id'])
        self.assertTrue(document.snapshot['partial']); self.assertEqual(len(document.snapshot['items']),1)
        self.assertEqual(document.snapshot['items'][0]['start_date'],str(self.today))
        text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(render_document_pdf(document))).pages)
        self.assertIn('Registro acumulado parcial',text); self.assertIn('PER-0',text); self.assertNotIn('PER-1',text)
        digest=document.content_hash
        quote.items.filter(equipment=first).update(end_date=self.today+timedelta(days=7))
        document.refresh_from_db(); self.assertEqual(snapshot_hash(document.snapshot),digest)

    def test_extension_can_extend_short_item_without_extending_other(self):
        quote=self.create_quote(); first,second=self.assets[:2]
        self.action(quote,'extend',[first.pk],new_end_date=str(self.today+timedelta(days=2)))
        self.assertEqual(quote.items.get(equipment=first).quantity_days,3)
        self.assertEqual(quote.items.get(equipment=second).end_date,self.today+timedelta(days=4))
        self.assertEqual(quote.end_date,self.today+timedelta(days=4))
        self.assertEqual(quote.extensions.get().item_changes[0]['equipment'],first.pk)
        self.assertEqual(quote.subtotal,Decimal('750'))

    def test_receipt_keeps_actor_of_each_partial_movement(self):
        quote=self.create_quote()
        for asset in self.assets[:2]: self.inspect(quote,asset)
        self.action(quote,'deliver',[self.assets[0].pk],delivered_at=(timezone.now()-timedelta(hours=1)).isoformat(),conditions='Primeira retirada')
        other=User.objects.create_user('second-period-operator@example.invalid','test',full_name='Outro operador',access_group=self.user.access_group)
        self.client.force_authenticate(other)
        self.action(quote,'deliver',[self.assets[1].pk],conditions='Segunda retirada')
        snapshot=snapshot_for(quote,'DELIVERY')
        self.assertEqual(snapshot['event_by'],'Outro operador')
        self.assertEqual(snapshot['event_conditions'],'Segunda retirada')
        self.assertEqual([item['delivered_by'] for item in snapshot['items']],['Operador','Outro operador'])

    def test_transport_batches_and_split_only_cover_selected_items(self):
        quote=self.create_quote(transport=True,same_start=True)
        task=quote.transport_tasks.get(leg='DELIVERY')
        first,second=list(quote.items.order_by('pk'))
        task.load_manifest = [first.equipment.internal_code, second.equipment.internal_code]
        task.save(update_fields=('load_manifest',))
        response=self.client.patch(f'/api/transport-tasks/{task.pk}/',{'rental_item_ids':[first.pk]},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(quote.transport_tasks.filter(leg='DELIVERY').count(),2)
        task.refresh_from_db(); self.assertEqual([line.pk for line in task_items(task)],[first.pk])
        self.assertEqual(task.load_manifest,[first.equipment.internal_code])
        self.inspect(quote,self.assets[0]); self.inspect(quote,self.assets[1])
        vehicle=Vehicle.objects.create(plate='ABC1D23',brand='Teste',model='Teste',capacity_kg=100)
        response=self.client.patch(f'/api/transport-tasks/{task.pk}/',{'vehicle':vehicle.pk,'driver':self.user.pk,'scheduled_at':timezone.now().isoformat()},format='json')
        self.assertEqual(response.status_code,200,response.data)
        response=self.client.post(f'/api/transport-tasks/{task.pk}/start/')
        self.assertEqual(response.status_code,200,response.data)  # Only 100 kg, rather than all 200 kg.
        self.action(quote,'deliver',[self.assets[0].pk],expected=400)
        self.assertEqual(self.client.post(f'/api/transport-tasks/{task.pk}/complete/').status_code,200)
        self.action(quote,'deliver',[self.assets[0].pk])
        self.action(quote,'deliver',[self.assets[1].pk],expected=400)
        self.assertEqual(quote.transport_tasks.filter(leg='RETURN').count(),1)
        self.assertEqual(quote.transport_tasks.get(leg='RETURN').rental_items.get().pk,first.pk)

    def test_transport_creates_distinct_days_and_extension_moves_only_own_pickup(self):
        quote=self.create_quote(transport=True)
        self.assertEqual(quote.transport_tasks.filter(leg='DELIVERY').count(),2)
        for asset in self.assets[:2]: self.inspect(quote,asset)
        quote.transport_tasks.update(status='COMPLETED')
        self.action(quote,'deliver',[asset.pk for asset in self.assets[:2]])
        old=quote.transport_tasks.get(leg='RETURN',rental_items__equipment=self.assets[0])
        self.action(quote,'extend',[self.assets[0].pk],new_end_date=str(self.today+timedelta(days=3)))
        old.refresh_from_db(); self.assertEqual(old.status,'CANCELLED')
        new=quote.transport_tasks.get(leg='RETURN',status='PLANNED',rental_items__equipment=self.assets[0])
        self.assertEqual(new.batch_date,self.today+timedelta(days=3))

    def test_two_nonoverlapping_reservations_do_not_block_each_other_preparation(self):
        quote=self.create_quote()
        data={'customer':self.customer.pk,'start_date':str(self.today+timedelta(days=2)),'end_date':str(self.today+timedelta(days=3)),
              'status':'APPROVED','conditions':'Teste','items':[{'equipment_id':self.assets[0].pk,'daily_rate':'100'}]}
        response=self.client.post('/api/rental-quotes/',data,format='json')
        self.assertEqual(response.status_code,201,response.data)
        self.inspect(quote,self.assets[0]); self.action(quote,'deliver',[self.assets[0].pk])
        other=RentalQuote.objects.get(pk=response.data['id']); self.inspect(other,self.assets[0])
        self.action(other,'deliver',[self.assets[0].pk],expected=400)  # Physical possession always wins.

    def test_report_and_dashboard_identify_overdue_item_inside_longer_quote(self):
        from ai.reports import build_operational_report
        quote=self.create_quote(); first=self.assets[0]
        quote.items.filter(equipment=first).update(start_date=self.today-timedelta(days=2),end_date=self.today-timedelta(days=1))
        self.inspect(quote,first); self.action(quote,'deliver',[first.pk])
        report=build_operational_report(self.today-timedelta(days=7),self.today,SimpleNamespace(ranking=lambda **kwargs: []))
        self.assertEqual(report['rentals']['late_returns'][0]['equipment'],[first.name])
        self.assertEqual(report['rentals']['late_returns'][0]['days_late'],1)
        dashboard=self.client.get('/api/dashboard/')
        self.assertEqual(dashboard.status_code,200,dashboard.data)
        self.assertEqual(dashboard.data['overdue_rentals'],1)
        self.action(quote,'return',[first.pk])
        report=build_operational_report(self.today-timedelta(days=7),self.today,SimpleNamespace(ranking=lambda **kwargs: []))
        self.assertEqual(report['rentals']['late_returns'],[])


class FreightPeriodTests(SimpleTestCase):
    @patch('rentals.freight.estimate_freight')
    def test_separate_days_are_priced_separately(self, estimate):
        estimate.return_value={'fee':'25.00','trip_count':1,'equipment_count':1}
        periods=[{'equipment_id':1,'start_date':'2026-11-02','end_date':'2026-11-04'},
                 {'equipment_id':2,'start_date':'2026-11-02','end_date':'2026-11-05'}]
        delivery=estimate_period_freight({},periods,leg='DELIVERY')
        self.assertEqual(delivery['fee'],'25.00'); self.assertEqual(estimate.call_count,1)
        estimate.reset_mock()
        pickup=estimate_period_freight({},periods,leg='RETURN')
        self.assertEqual(pickup['fee'],'50.00'); self.assertEqual(pickup['trip_count'],2)
        self.assertEqual(estimate.call_count,2)

    @patch('rentals.freight.estimate_freight')
    def test_unresolved_route_never_becomes_zero_fee(self, estimate):
        estimate.return_value={'fee':None,'requires_location_confirmation':True}
        result=estimate_period_freight({},[{'equipment_id':1,'start_date':'2026-11-02'}],leg='DELIVERY')
        self.assertIsNone(result['fee']); self.assertTrue(result['requires_location_confirmation'])
