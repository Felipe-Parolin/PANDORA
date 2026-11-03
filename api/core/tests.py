from django.db import connection
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from accounts.models import AccessGroup, User
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


class DashboardPermissionTests(TestCase):
    def setUp(self):
        self.group = AccessGroup.objects.create(name="Painel restrito", permissions=["dashboard.view", "logistics.view"])
        self.user = User.objects.create_user("dashboard@example.invalid", "test", full_name="Transporte", access_group=self.group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_transport_dashboard_does_not_expose_other_domains(self):
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("agenda_next_7_days", response.data)
        for field in ("customers", "equipment", "recent_quotes", "quotes_total", "open_orders", "realized_revenue"):
            self.assertNotIn(field, response.data)

    def test_permission_change_updates_dashboard_payload(self):
        self.group.permissions = ["dashboard.view", "rentals.view"]
        self.group.save()
        self.user.refresh_from_db()
        response = self.client.get("/api/dashboard/")
        self.assertIn("quotes_total", response.data)
        self.assertIn("conversion_percent", response.data)
        self.assertIn("rentals_in_progress", response.data)
        self.assertNotIn("agenda_next_7_days", response.data)
        self.assertNotIn("equipment", response.data)

    def test_dashboard_permission_alone_has_no_domain_data(self):
        self.group.permissions = ["dashboard.view"]
        self.group.save()
        self.user.refresh_from_db()
        self.assertEqual(self.client.get("/api/dashboard/").data, {})


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


    def test_order_creator_and_assigned_technician_are_not_notified_twice(self):
        order = ServiceOrder.objects.create(
            equipment=self.equipment, maintenance_type=ServiceOrder.Type.CORRECTIVE,
            symptoms="Falha de partida", opened_by=self.technician, technician=self.technician,
        )
        titles = list(Notification.objects.filter(recipient=self.technician).values_list("title", flat=True))
        self.assertEqual(titles, [f"Chamado atribuído: {order.number}"])

    def test_unread_filter_lists_only_unread_notifications(self):
        ServiceOrder.objects.create(equipment=self.equipment, maintenance_type=ServiceOrder.Type.CORRECTIVE, symptoms="Falha de partida")
        client = APIClient()
        client.force_authenticate(user=self.technician)
        self.assertEqual(len(client.get("/api/notifications/?status=unread").data["results"]), 1)
        client.post("/api/notifications/read-all/")
        self.assertEqual(len(client.get("/api/notifications/?status=unread").data["results"]), 0)
        self.assertEqual(len(client.get("/api/notifications/").data["results"]), 1)

    def test_delete_is_private_and_updates_unread_count(self):
        notice = Notification.objects.create(recipient=self.technician, kind="RENTAL", title="Reserva", message="Teste", target_url="/locacoes", event_key="delete-test")
        client = APIClient()
        self.assertEqual(client.delete(f"/api/notifications/{notice.pk}/").status_code, 401)
        client.force_authenticate(self.other)
        self.assertEqual(client.delete(f"/api/notifications/{notice.pk}/").status_code, 404)
        self.assertTrue(Notification.objects.filter(pk=notice.pk).exists())
        client.force_authenticate(self.technician)
        self.assertEqual(client.delete(f"/api/notifications/{notice.pk}/").status_code, 204)
        self.assertEqual(client.get("/api/notifications/").data["unread_count"], 0)

    def test_kind_tabs_filter_before_pagination_and_keep_private_counts(self):
        Notification.objects.bulk_create([
            Notification(recipient=self.technician, kind="MAINTENANCE", title="OS", message="Teste", target_url="/manutencao", event_key=f"tab-{index}") for index in range(31)
        ])
        rental = Notification.objects.create(recipient=self.technician, kind="RENTAL", title="Reserva", message="Teste", target_url="/locacoes", event_key="tab-rental")
        Notification.objects.create(recipient=self.other, kind="TRANSPORT", title="Privado", message="Teste", target_url="/transporte", event_key="tab-private")
        client = APIClient()
        client.force_authenticate(self.technician)
        response = client.get("/api/notifications/?kind=RENTAL")
        self.assertEqual([item["id"] for item in response.data["results"]], [rental.pk])
        self.assertEqual(response.data["counts"], {"RENTAL": 1, "MAINTENANCE": 31})
        self.assertEqual(response.data["unread_count"], 32)
        first = client.get("/api/notifications/?kind=MAINTENANCE").data
        second = client.get("/api/notifications/?kind=MAINTENANCE&page=2").data
        self.assertEqual(len(first["results"]), 30)
        self.assertEqual(first["next_page"], 2)
        self.assertEqual(len(second["results"]), 1)
        self.assertIsNone(second["next_page"])
        for query in ("kind=UNKNOWN", "page=0", "page=abc"):
            self.assertEqual(client.get(f"/api/notifications/?{query}").status_code, 400)
