from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AccessGroup, User
from .models import Equipment, EquipmentCategory


class EquipmentQRTests(TestCase):
    def setUp(self):
        group = AccessGroup.objects.create(name="Frota", permissions=["assets.view"])
        user = User.objects.create_user("fleet@example.com", "strong-password", full_name="Frota", access_group=group)
        category = EquipmentCategory.objects.create(name="Teste QR", default_daily_rate=100)
        self.equipment = Equipment.objects.create(category=category, name="Compactador", brand="Marca", model="M1", serial_number="QR-001", internal_code="EQ-QR", daily_rate=100)
        self.client = APIClient()
        self.client.force_authenticate(user)

    def test_qr_endpoint_returns_png_and_resolves_token(self):
        image = self.client.get(f"/api/equipment/{self.equipment.id}/qr-code/")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image["Content-Type"], "image/png")
        self.assertGreater(len(image.content), 100)

        resolved = self.client.get(f"/api/equipment/resolve-qr/?token={self.equipment.qr_code_token}")
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.data["internal_code"], "EQ-QR")
