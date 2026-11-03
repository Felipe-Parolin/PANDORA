from io import StringIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User, AccessGroup
from ai.models import AIConsultation, ManualChunk, UnfulfilledDemand
from assets.models import Equipment, EquipmentCategory, MediaAsset
from commercial.models import Receivable, Payment, MarketingCampaign, PurchaseRecommendation
from core.models import Notification
from customers.models import Customer
from logistics.models import TransportTask, Vehicle
from maintenance.models import ServiceOrder, MaintenancePlan
from rentals.models import RentalQuote, RentalItem, RentalDocument


@override_settings(DEBUG=True,AI_ENABLED=False,GEOCODING_ENABLED=False)
class DemoDataTests(TestCase):
    def test_full_demo_is_consistent_repeatable_and_preserves_existing_access_and_edits(self):
        if connection.vendor!='postgresql':self.skipTest('A carga é específica para PostgreSQL local')
        group=AccessGroup.objects.create(name='Admin preservado na demonstração',permissions=['*'])
        admin=User.objects.create_user('admin@pandora.local','Original-only-for-test',full_name='Admin preservado',role='ADMIN',access_group=group)
        initial=(admin.password,admin.access_group_id,admin.full_name,admin.is_superuser)
        temporary=tempfile.TemporaryDirectory(prefix='pandora-demo-test-')
        self.assertTrue(Path(temporary.name).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(temporary.cleanup)
        with override_settings(MEDIA_ROOT=temporary.name),patch('requests.sessions.Session.request',side_effect=AssertionError('A carga não pode acessar serviços externos')):
            output=StringIO()
            call_command('seed_realistic_demo',password='Only-for-demo-test-123',stdout=output)
            admin.refresh_from_db()
            self.assertEqual((admin.password,admin.access_group_id,admin.full_name,admin.is_superuser),initial)
            self.assertNotIn('Only-for-demo-test-123',output.getvalue())
            self.assertGreaterEqual(Customer.objects.count(),18)
            self.assertEqual(Equipment.objects.count(),30)
            self.assertEqual(EquipmentCategory.objects.count(),12)
            self.assertEqual(Vehicle.objects.count(),12)
            self.assertEqual(RentalQuote.objects.count(),26)
            self.assertEqual(set(RentalQuote.objects.values_list('status',flat=True)),set(RentalQuote.Status.values))
            self.assertTrue(RentalItem.objects.filter(quote__number='ORC-CEN-007',stage='PENDING').exists())
            self.assertTrue(RentalItem.objects.filter(quote__number='ORC-CEN-008',stage='COMPLETED').exists())
            self.assertTrue(TransportTask.objects.filter(status='IN_TRANSIT').exists())
            self.assertTrue(TransportTask.objects.filter(items_scoped=True).exists())
            self.assertTrue(ManualChunk.objects.exists())
            self.assertGreaterEqual(AIConsultation.objects.count(),12)
            self.assertGreaterEqual(UnfulfilledDemand.objects.count(),36)
            self.assertEqual(MarketingCampaign.objects.count(),12)
            self.assertFalse(MarketingCampaign.objects.exclude(status='DRAFT').exists())
            self.assertGreaterEqual(PurchaseRecommendation.objects.count(),12)
            self.assertTrue(Receivable.objects.filter(status='OPEN').exists())
            self.assertEqual(Payment.objects.count(),2)
            self.assertGreaterEqual(RentalDocument.objects.count(),7)
            for line in RentalItem.objects.select_related('quote'):
                self.assertLessEqual(line.start_date,line.end_date)
                self.assertEqual(line.quantity_days,(line.end_date-line.start_date).days+1)
            for order in ServiceOrder.objects.all():order.full_clean()
            for task in TransportTask.objects.filter(items_scoped=True):self.assertTrue(task.rental_items.exists())
            client=APIClient();client.force_authenticate(admin)
            for url in ['/api/dashboard/','/api/rental-quotes/','/api/transport-tasks/','/api/receivables/','/api/receivables/customers/','/api/purchase-recommendations/','/api/ai/consultations/']:
                self.assertEqual(client.get(url).status_code,200,url)
            for payment in Payment.objects.all():self.assertEqual(client.get(f'/api/payments/{payment.pk}/receipt/').status_code,200)
            # Não desfaz edição, avanço de uma locação ou alteração de senha feita pelo testador.
            quote=RentalQuote.objects.get(number='ORC-CEN-006');quote.status='DRAFT';quote.save(update_fields=['status'])
            item=Equipment.objects.get(internal_code='EQ-007');item.name='Nome alterado no teste';item.save(update_fields=['name'])
            models=[User,Customer,Equipment,EquipmentCategory,Vehicle,RentalQuote,RentalItem,ServiceOrder,MaintenancePlan,MediaAsset,Receivable,Payment,RentalDocument,AIConsultation,UnfulfilledDemand,Notification,MarketingCampaign,PurchaseRecommendation]
            before={model.__name__:model.objects.count() for model in models}
            call_command('seed_realistic_demo',password='Different-test-password',stdout=StringIO())
            after={model.__name__:model.objects.count() for model in models}
            self.assertEqual(before,after)
            quote.refresh_from_db();item.refresh_from_db();admin.refresh_from_db()
            self.assertEqual(quote.status,'DRAFT');self.assertEqual(item.name,'Nome alterado no teste');self.assertEqual(admin.password,initial[0])

    @override_settings(DEBUG=False)
    def test_seed_refuses_non_development_database_without_writing(self):
        with self.assertRaises(CommandError):call_command('seed_realistic_demo',password='Only-for-test-123',stdout=StringIO())
        self.assertFalse(Equipment.objects.exists())
