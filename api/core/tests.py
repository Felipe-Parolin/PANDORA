from django.db import connection
from django.utils import timezone
from datetime import timedelta
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from maintenance.models import ServiceOrder
from customers.models import Customer
from rentals.models import RentalItem, RentalQuote, UnmetRentalDemand
from .models import Notification

from .patterns import AIService, AISettings
from .recommendations import suggest_equipment_purchase


class SingletonPatternTests(SimpleTestCase):
    def test_configuration_is_unique_per_process(self):
        first = AISettings.get_instance()
        second = AISettings.instance()
        self.assertIs(first, second)
        self.assertIs(AIService().get_configuration(), first)


class HealthTests(TestCase):
    def test_health_checks_database_connection(self):
        response = APIClient().get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["database"], connection.vendor)


class PurchaseSuggestionTests(TestCase):
    def test_suggestion_requires_rental_history_and_shows_evidence(self):
        self.assertEqual(suggest_equipment_purchase()["status"], "INSUFFICIENT_DATA")
        seller = User.objects.create_user(email="seller@example.invalid", password="test", full_name="Vendas", role=User.Role.SALES)
        customer = Customer.objects.create(person_type="PF", name="Cliente", document="12345678909", phone="19999999999")
        category = EquipmentCategory.objects.create(name="Cortadoras", default_daily_rate=100)
        equipment = Equipment.objects.create(category=category, name="Cortadora", brand="Teste", model="C1", serial_number="PURCHASE-1", internal_code="EQ-P1", status=Equipment.Status.MAINTENANCE, daily_rate=100)
        quote = RentalQuote.objects.create(customer=customer, start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=2), created_by=seller)
        RentalItem.objects.create(quote=quote, equipment=equipment, daily_rate=100, quantity_days=3)
        result = AIService().suggest_purchase()
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["equipment_id"], equipment.id)
        self.assertEqual(result["evidence"]["category_available"], 0)
        self.assertEqual(result["evidence"]["requested_days"], 3)
        self.assertEqual(result["confidence"], "LOW")
        admin = User.objects.create_user(email="admin@example.invalid", password="test", full_name="Admin", role=User.Role.ADMIN)
        client = APIClient()
        client.force_authenticate(admin)
        dashboard = client.get("/api/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["purchase_suggestion"]["equipment_id"], equipment.id)

    def test_recommendation_uses_utilization_lost_demand_and_maintenance_cost(self):
        seller = User.objects.create_user(email="purchasing@example.invalid", password="test", full_name="Vendas", role=User.Role.SALES)
        customer = Customer.objects.create(person_type="PF", name="Cliente", document="12345678909", phone="19999999999")
        category = EquipmentCategory.objects.create(name="Geradores", default_daily_rate=100)
        equipment = Equipment.objects.create(
            category=category, name="Gerador", brand="Teste", model="G1", serial_number="PURCHASE-2",
            internal_code="EQ-P2", daily_rate=100, acquisition_cost=1000,
        )
        today = timezone.localdate()
        quote = RentalQuote.objects.create(customer=customer, start_date=today - timedelta(days=4), end_date=today - timedelta(days=2), status=RentalQuote.Status.COMPLETED, created_by=seller)
        RentalItem.objects.create(quote=quote, equipment=equipment, daily_rate=100, quantity_days=3)
        UnmetRentalDemand.objects.create(equipment=equipment, customer=customer, start_date=today, end_date=today + timedelta(days=2), reason="Indisponível", created_by=seller)
        ServiceOrder.objects.create(equipment=equipment, maintenance_type=ServiceOrder.Type.CORRECTIVE, symptoms="Reparo", labor_cost=250, parts_cost=200, opened_by=seller)
        result = suggest_equipment_purchase()
        self.assertEqual(result["recommendation_type"], "REPLACEMENT")
        self.assertEqual(result["evidence"]["unmet_demand"], 1)
        self.assertEqual(result["evidence"]["maintenance_cost"], "450.00")
        self.assertEqual(result["evidence"]["acquisition_cost"], "1000.00")
        self.assertGreater(result["evidence"]["utilization_percent"], 0)


class NotificationTests(TestCase):
    def setUp(self):
        self.technician = User.objects.create_user(email="tech@example.invalid", password="test", full_name="Técnico", role=User.Role.MAINTENANCE)
        self.other = User.objects.create_user(email="sales@example.invalid", password="test", full_name="Vendas", role=User.Role.SALES)
        category = EquipmentCategory.objects.create(name="Teste", default_daily_rate=100)
        self.equipment = Equipment.objects.create(category=category, name="Gerador", brand="Teste", model="G1", serial_number="TEST-1", internal_code="EQ-T1", daily_rate=100)

    def test_new_order_notifies_only_staff_with_maintenance_access(self):
        order = ServiceOrder.objects.create(equipment=self.equipment, maintenance_type=ServiceOrder.Type.CORRECTIVE, symptoms="Falha de partida", opened_by=self.other)
        self.assertEqual(Notification.objects.filter(recipient=self.technician).count(), 1)
        self.assertFalse(Notification.objects.filter(recipient=self.other).exists())
        notice = Notification.objects.get(recipient=self.technician)
        self.assertIn(str(order.pk), notice.target_url)

    def test_notifications_are_private_and_can_be_marked_read(self):
        order = ServiceOrder.objects.create(equipment=self.equipment, maintenance_type=ServiceOrder.Type.CORRECTIVE, symptoms="Falha de partida")
        notice = Notification.objects.get(recipient=self.technician)
        client = APIClient()
        client.force_authenticate(user=self.other)
        self.assertEqual(client.get("/api/notifications/").data["unread_count"], 0)
        self.assertEqual(client.post(f"/api/notifications/{notice.pk}/read/").status_code, 404)
        client.force_authenticate(user=self.technician)
        self.assertEqual(client.get("/api/notifications/").data["unread_count"], 1)
        self.assertEqual(client.post(f"/api/notifications/{notice.pk}/read/").status_code, 200)
        self.assertEqual(client.get("/api/notifications/").data["unread_count"], 0)
        self.assertEqual(client.post("/api/notifications/read-all/").data["marked_read"], 0)
