from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from customers.models import Customer
from maintenance.models import ServiceOrder
from rentals.models import RentalInspection, RentalItem, RentalQuote
from rentals.services import availability_reason


class QuoteEditingAvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('edit-quote@example.invalid', full_name='Teste', role=User.Role.ADMIN)
        cls.customer = Customer.objects.create(name='Cliente de teste', person_type='PF', document='12345678909', phone='19999999999')
        cls.category = EquipmentCategory.objects.create(name='Categoria de teste')
        cls.first = Equipment.objects.create(category=cls.category, name='Equipamento existente', internal_code='EDIT-1', serial_number='EDIT-S1', daily_rate=100)
        cls.second = Equipment.objects.create(category=cls.category, name='Equipamento adicional', internal_code='EDIT-2', serial_number='EDIT-S2', daily_rate=200)

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.quote = RentalQuote.objects.create(customer=self.customer, start_date=timezone.localdate(), end_date=timezone.localdate()+timedelta(days=2), status='SENT', conditions='Retirada na loja', created_by=self.user)
        RentalItem.objects.create(quote=self.quote, equipment=self.first, daily_rate=100, quantity_days=3, total=300)
        self.params = {'start': str(self.quote.start_date), 'end': str(self.quote.end_date), 'ignore_quote': self.quote.pk}

    def test_own_reservation_and_pending_pre_inspection_do_not_block_its_equipment(self):
        self.quote.status = 'APPROVED'; self.quote.save()
        self.first.status = 'RESERVED'; self.first.save()
        inspection = RentalInspection.objects.create(quote=self.quote, equipment=self.first, inspection_type='PRE_RENTAL')
        ServiceOrder.objects.create(equipment=self.first, maintenance_type='PRE_RENTAL', rental_inspection=inspection, symptoms='Inspeção da própria reserva')
        response = self.client.get('/api/rental-quotes/availability/', self.params)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(self.first.pk, [row['equipment']['id'] for row in response.data['available']])
        self.assertIsNone(availability_reason(self.first, self.quote.start_date, self.quote.end_date, self.quote))

    def test_sent_quote_keeps_existing_maintenance_item_and_adds_an_available_item_without_reserving(self):
        ServiceOrder.objects.create(equipment=self.first, maintenance_type='CORRECTIVE', status='ABANDONED', technician=self.user, abandoned_reason='Peça pendente', symptoms='Reparar')
        response = self.client.patch(f'/api/rental-quotes/{self.quote.pk}/', {'items': [{'equipment_id': self.first.pk, 'daily_rate': '100'}, {'equipment_id': self.second.pk, 'daily_rate': '200'}]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, 'SENT')
        self.assertEqual(self.quote.items.count(), 2)
        self.assertFalse(self.quote.inspections.exists())
        approval = self.client.post(f'/api/rental-quotes/{self.quote.pk}/reserve/')
        self.assertEqual(approval.status_code, 400, approval.data)
        self.quote.refresh_from_db(); self.assertEqual(self.quote.status, 'SENT')

    def test_availability_and_categories_both_block_pending_final_inspection(self):
        self.first.status = 'INSPECTION'; self.first.save()
        response = self.client.get('/api/rental-quotes/availability/', {**self.params, 'equipment_ids': str(self.first.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['available'], [])
        self.assertEqual(response.data['blocked'][0]['equipment']['id'], self.first.pk)
        categories = self.client.get('/api/rental-quotes/availability-categories/', self.params)
        self.assertEqual(categories.status_code, 200)
        self.assertEqual(categories.data['results'][0]['available'], 1)
