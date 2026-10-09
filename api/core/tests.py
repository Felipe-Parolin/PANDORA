from django.db import connection
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from maintenance.models import ServiceOrder
from .models import Notification

from .patterns import AIService, AISettings


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
