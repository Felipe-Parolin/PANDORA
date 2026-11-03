from datetime import timedelta
from io import BytesIO
from unittest.mock import patch, MagicMock
from urllib.parse import parse_qs, urlparse
import json

from django.core.cache import cache
from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient
from accounts.models import User, AccessGroup
from assets.models import Equipment, EquipmentCategory
from customers.models import Customer
from logistics.geo import geocode_precise_address
from rentals.models import RentalQuote, RentalInspection, RentalDocument
from rentals.documents import render_document_pdf
from rentals.freight import estimate_period_freight, estimate_freight


class DestinationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        group=AccessGroup.objects.create(name='Destinos',permissions=['*'])
        cls.user=User.objects.create_user('destinations@example.invalid','test',full_name='Operador',access_group=group)
        cls.customer=Customer.objects.create(name='Cliente de teste',person_type='PF',document='12345678909',phone='19999999999')
        category=EquipmentCategory.objects.create(name='Destinos')
        cls.assets=[Equipment.objects.create(name=f'Item {i}',internal_code=f'DEST-{i}',serial_number=f'DEST-{i}',category=category,daily_rate=100,estimated_weight_kg=50) for i in range(3)]
        cls.today=timezone.localdate()

    def setUp(self):
        self.client=APIClient();self.client.force_authenticate(self.user)

    def location(self,address='Rua de teste, Bairro, Leme/SP',number='200',clock='10:00'):
        return {'address':address,'number':number,'cep':'13614032','complement':'Portão lateral','time':clock}

    def payload(self):
        return {'customer':self.customer.pk,'start_date':str(self.today),'end_date':str(self.today+timedelta(days=1)),
                'status':'APPROVED','conditions':'Teste de destinos','delivery_transport_required':True,'return_transport_required':True,
                'delivery_address':'Rua de teste, Bairro, Leme/SP','delivery_number':'100','delivery_cep':'13614032',
                'return_address':'Rua de teste, Bairro, Leme/SP','return_number':'100','return_cep':'13614032',
                'items':[{'equipment_id':asset.pk,'daily_rate':'100'} for asset in self.assets]}

    def create(self,payload):
        response=self.client.post('/api/rental-quotes/',payload,format='json')
        self.assertEqual(response.status_code,201,response.data)
        return RentalQuote.objects.get(pk=response.data['id'])

    def test_same_day_different_numbers_and_hours_create_separate_stops(self):
        data=self.payload()
        data['items'][0]['delivery_location']=self.location(number='200',clock='08:00')
        data['items'][1]['delivery_location']=self.location(number='200',clock='11:00')
        data['items'][2]['delivery_location']=self.location(number='300',clock='08:00')
        quote=self.create(data)
        tasks=list(quote.transport_tasks.order_by('pk'))
        self.assertEqual(len(tasks),3)
        self.assertEqual([timezone.localtime(task.scheduled_at).strftime('%H:%M') for task in tasks],['08:00','11:00','08:00'])
        self.assertIn(', 300,',tasks[2].address)
        self.assertTrue(all(task.address_cep=='13614032' for task in tasks))
        self.assertTrue(all(task.rental_items.count()==1 for task in tasks))

    def test_identical_destination_shares_trip_and_custom_time_can_be_unscheduled(self):
        data=self.payload()
        data['items'][0]['delivery_location']=self.location(clock='')
        data['items'][1]['delivery_location']=self.location(clock='')
        data['items'][2]['delivery_location']=self.location(clock='11:00')
        quote=self.create(data)
        self.assertEqual(quote.transport_tasks.filter(leg='DELIVERY').count(),2)
        self.assertEqual(quote.transport_tasks.get(scheduled_at__isnull=True).rental_items.count(),2)

    def test_partial_delivery_creates_only_its_pickup_at_its_address_and_time(self):
        data=self.payload();data['items'][1]['return_location']=self.location('Rua de coleta, Centro, Leme/SP','900','16:30')
        quote=self.create(data)
        quote.transport_tasks.update(status='COMPLETED')
        inspection=quote.inspections.get(equipment=self.assets[1],inspection_type='PRE_RENTAL')
        response=self.client.patch(f'/api/rental-inspections/{inspection.pk}/',{'result':'APPROVED','checklist':[{**item,'status':'OK'} for item in inspection.checklist]},format='json')
        self.assertEqual(response.status_code,200,response.data)
        response=self.client.post(f'/api/rental-quotes/{quote.pk}/deliver/',{'equipment_ids':[self.assets[1].pk]},format='json')
        self.assertEqual(response.status_code,200,response.data)
        pickup=quote.transport_tasks.get(leg='RETURN')
        self.assertEqual(pickup.rental_items.get().equipment_id,self.assets[1].pk)
        self.assertEqual(pickup.address,'Rua de coleta, 900, Centro, Leme/SP')
        self.assertEqual(timezone.localtime(pickup.scheduled_at).strftime('%H:%M'),'16:30')
        self.assertEqual(timezone.localdate(pickup.scheduled_at),quote.end_date)

    def test_invalid_location_never_creates_quote(self):
        for invalid in ([],{'address':False},{'address':'Rua','number':{'value':100}},{'address':'Rua','time':'25:20'},{'address':'Rua','cep':'123'},{'address':'Rua','unknown':'x'}):
            data=self.payload();data['items'][0]['delivery_location']=invalid
            response=self.client.post('/api/rental-quotes/',data,format='json')
            self.assertEqual(response.status_code,400,response.data)
        self.assertFalse(RentalQuote.objects.exists())

    def test_same_day_time_validation_uses_item_override(self):
        data=self.payload();data['end_date']=data['start_date']
        data['items'][0]['delivery_location']=self.location(clock='15:00')
        data['items'][0]['return_location']=self.location(clock='08:00')
        response=self.client.post('/api/rental-quotes/',data,format='json')
        self.assertEqual(response.status_code,400,response.data)

    def test_addresses_cannot_change_after_reservation_and_document_keeps_them(self):
        data=self.payload();data['items'][0]['delivery_location']=self.location('Rua específica, Centro, Leme/SP','350','08:30')
        quote=self.create(data)
        response=self.client.patch(f'/api/rental-quotes/{quote.pk}/',{'delivery_number':'999'},format='json')
        self.assertEqual(response.status_code,400,response.data)
        response=self.client.post(f'/api/rental-quotes/{quote.pk}/documents/',{'kind':'QUOTE'},format='json')
        self.assertEqual(response.status_code,201,response.data)
        document=RentalDocument.objects.get(pk=response.data['id'])
        text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(render_document_pdf(document))).pages)
        self.assertIn('Rua específica, 350',text);self.assertIn('08:30',text)
        quote.items.filter(equipment=self.assets[0]).update(delivery_location=self.location(number='900'))
        self.assertEqual(render_document_pdf(document),render_document_pdf(RentalDocument.objects.get(pk=document.pk)))

    def test_whatsapp_preview_includes_item_destination_without_sending(self):
        data=self.payload();data['items'][0]['delivery_location']=self.location('Rua específica, Centro, Leme/SP','350','08:30')
        quote=self.create(data)
        response=self.client.get(f'/api/rental-quotes/{quote.pk}/whatsapp-link/')
        self.assertEqual(response.status_code,200,response.data)
        message=parse_qs(urlparse(response.data['url']).query)['text'][0]
        self.assertIn('Rua específica, 350',message);self.assertIn('08:30',message)
        self.assertFalse(response.data['automatic_send'])


class StructuredGeocodeTests(SimpleTestCase):
    def setUp(self): cache.clear()

    @patch('logistics.geo._throttle')
    @patch('logistics.geo.urlopen')
    def test_number_and_street_are_structured_without_free_query(self,urlopen,_throttle):
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps([
            {'lat':'-22.18','lon':'-47.38','address':{'house_number':'999'}},
            {'lat':'-22.19','lon':'-47.39','address':{'house_number':'120'}},
        ]).encode();urlopen.return_value=response
        point=geocode_precise_address('Rua de teste, Bairro, Leme/SP',number='120',destination={'street':'Rua de teste','city':'Leme','state':'SP','cep':'13614032'})
        self.assertEqual(point,(-22.19,-47.39))
        params=parse_qs(urlparse(urlopen.call_args.args[0].full_url).query)
        self.assertEqual(params['street'],['120 Rua de teste']);self.assertNotIn('q',params)

    @patch('logistics.geo.geocode_precise_address',return_value=None)
    @patch('rentals.freight.freight_origin',return_value=(-22.1757125,-47.3820152))
    @patch('logistics.routing.road_route',return_value={'distance_m':1000,'duration_seconds':120})
    def test_missing_house_automatically_uses_same_street_with_estimate_label(self,route,origin,precise):
        result=estimate_freight({'street':'Rua de teste','cep':'13614032','city':'Leme','state':'SP','latitude':-22.18,'longitude':-47.38},address='Rua de teste, Bairro, Leme/SP',number='120')
        self.assertEqual(result['fee'],'25.00');self.assertTrue(result['approximate_destination'])
        self.assertNotIn('requires_location_confirmation',result)

    @patch('rentals.freight.estimate_freight',return_value={'fee':'25.00','trip_count':1})
    def test_same_destination_different_time_is_separate_trip(self,estimate):
        result=estimate_period_freight({},[{'equipment_id':1,'start_date':'2026-11-02','time':'08:00'},{'equipment_id':2,'start_date':'2026-11-02','time':'11:00'},{'equipment_id':3,'start_date':'2026-11-02','time':'08:00'}],leg='DELIVERY')
        self.assertEqual(result['fee'],'50.00');self.assertEqual(result['trip_count'],2)
