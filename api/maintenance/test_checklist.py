from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from .models import MaintenanceActivity, ServiceOrder


class OrderChecklistTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("checklist@example.invalid", full_name="Técnico", role=User.Role.MAINTENANCE)
        category = EquipmentCategory.objects.create(name="Teste", default_daily_rate=100)
        equipment = Equipment.objects.create(category=category, name="Motor", brand="M", model="M1", serial_number="CHK-1", internal_code="CHK-1", daily_rate=100)
        self.order = ServiceOrder.objects.create(equipment=equipment, opened_by=self.user, symptoms="Revisar", maintenance_type="CORRECTIVE")
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.url = f"/api/service-orders/{self.order.pk}/"

    def test_create_points_update_progress_and_preserve_omitted_history(self):
        response = self.client.patch(self.url, {"activities": [{"description": "Verificar proteção", "completed": False}, {"description": "Teste final", "completed": False}]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        first, second = response.data["activities"]
        response = self.client.patch(self.url, {"activities": [{"id": first["id"], "description": first["description"], "completed": True}]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.order.activities.count(), 2)
        self.assertTrue(self.order.activities.get(pk=first["id"]).completed)
        self.assertFalse(self.order.activities.get(pk=second["id"]).completed)

    def test_incomplete_checklist_prevents_closure_including_omitted_points(self):
        point = MaintenanceActivity.objects.create(service_order=self.order, description="Testar", completed=False)
        response = self.client.patch(self.url, {"status": "COMPLETED", "diagnosis": "Não deve gravar"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db(); self.assertEqual(self.order.diagnosis, "")
        response = self.client.patch(self.url, {"status": "COMPLETED", "activities": [{"id": point.pk, "description": "Testar", "completed": True}]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_cannot_change_a_point_from_another_order_or_repeat_ids(self):
        other = ServiceOrder.objects.create(equipment=self.order.equipment, symptoms="Outro", maintenance_type="CORRECTIVE")
        point = MaintenanceActivity.objects.create(service_order=other, description="Outro atendimento")
        for points in ([{"id": point.pk, "description": "Alterar", "completed": True}], [{"id": point.pk, "description": "A"}] * 2):
            response = self.client.patch(self.url, {"activities": points}, format="json")
            self.assertEqual(response.status_code, 400)
        point.refresh_from_db(); self.assertFalse(point.completed)

    def test_readonly_cannot_write_checklist(self):
        from accounts.models import AccessGroup
        group = AccessGroup.objects.create(name="Consulta técnica", permissions=["maintenance.view"])
        self.user.access_group = group; self.user.save(); self.client.force_authenticate(self.user)
        self.assertEqual(self.client.patch(self.url, {"activities": [{"description": "Testar"}]}, format="json").status_code, 403)

    def test_starting_scheduled_preventive_order_blocks_equipment(self):
        from rentals.services import refresh_equipment_status
        self.order.maintenance_type = "PREVENTIVE"; self.order.status = "SCHEDULED"; self.order.save()
        self.assertEqual(refresh_equipment_status(self.order.equipment), Equipment.Status.AVAILABLE)
        response = self.client.patch(self.url, {"status": "IN_PROGRESS", "technician": self.user.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.order.equipment.refresh_from_db()
        self.assertEqual(self.order.equipment.status, Equipment.Status.MAINTENANCE)
