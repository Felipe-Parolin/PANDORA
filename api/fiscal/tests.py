from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccessGroup, User
from assets.models import Equipment, EquipmentCategory
from core.models import AuditLog
from customers.models import Customer
from rentals.models import RentalItem, RentalQuote
from .models import FiscalCompany, FiscalCustomerData, FiscalEquipmentData


class FiscalPreparationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("fiscal@example.invalid", "test", full_name="Administrador", role=User.Role.ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.customer = Customer.objects.create(person_type="PF", name="Cliente fictício", document="12345678909", phone="19999999999", address="Endereço legado preservado")
        category = EquipmentCategory.objects.create(name="Categoria", default_daily_rate=100)
        self.equipment = Equipment.objects.create(category=category, name="Equipamento", brand="Teste", model="T1", serial_number="FISCAL-1", internal_code="EQ-FISCAL", daily_rate=100)
        self.quote = RentalQuote.objects.create(customer=self.customer, created_by=self.admin, start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=2))
        RentalItem.objects.create(quote=self.quote, equipment=self.equipment, daily_rate=100, quantity_days=3, total=300)
        self.quote.recalculate()
        self.address = {"postal_code": "01001000", "street": "Rua de teste", "number": "10", "neighborhood": "Centro", "city": "São Paulo", "state": "SP", "municipality_code": "3550308"}

    def test_company_starts_blank_and_get_does_not_create_a_record(self):
        response = self.client.get("/api/fiscal/company/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["company"]["cnpj"], "")
        self.assertEqual(response.data["company"]["legal_name"], "")
        self.assertFalse(response.data["transmission_enabled"])
        self.assertFalse(FiscalCompany.objects.exists())
        self.assertEqual(self.client.post("/api/fiscal/company/", {}, format="json").status_code, 405)

    def test_acl_separates_read_profile_changes_and_issuer_configuration(self):
        group = AccessGroup.objects.create(name="Fiscal consulta", permissions=["fiscal.view"])
        reader = User.objects.create_user("reader@example.invalid", "test", full_name="Consulta", access_group=group)
        self.client.force_authenticate(reader)
        self.assertEqual(self.client.get("/api/fiscal/rentals/").status_code, 200)
        self.assertEqual(self.client.patch("/api/fiscal/company/", {"legal_name": "Bloqueado"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/fiscal/customers/{self.customer.id}/", self.address, format="json").status_code, 403)
        group.permissions = ["fiscal.view", "fiscal.manage"]
        group.save()
        reader.refresh_from_db()
        self.client.force_authenticate(reader)
        self.assertEqual(self.client.patch(f"/api/fiscal/customers/{self.customer.id}/", self.address, format="json").status_code, 200)
        self.assertEqual(self.client.patch("/api/fiscal/company/", {}, format="json").status_code, 403)
        group.permissions = []
        group.save()
        reader.refresh_from_db()
        self.client.force_authenticate(reader)
        self.assertEqual(self.client.get(f"/api/fiscal/rentals/{self.quote.id}/export/").status_code, 403)

    def test_readiness_does_not_guess_legacy_address_or_tax_rules(self):
        response = self.client.get(f"/api/fiscal/rentals/{self.quote.id}/readiness/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data_ready"])
        self.assertFalse(response.data["can_issue"])
        self.assertFalse(response.data["taxes_calculated"])
        self.assertEqual(response.data["customer"]["legacy_address"], self.customer.address)
        self.assertEqual(response.data["customer"]["fiscal"]["street"], "")
        self.assertTrue(any(item["field"] == "tax_regime" for item in response.data["issues"]))
        self.assertFalse(FiscalCustomerData.objects.exists())

    def test_complete_basic_data_still_requires_fiscal_integration(self):
        issuer = {**self.address, "legal_name": "Emitente fictício", "cnpj": "12.ABC.345/01DE-35", "tax_regime": "SIMPLE", "icms_status": "NON_CONTRIBUTOR", "cnae": "7732201"}
        response = self.client.patch("/api/fiscal/company/", issuer, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["company"]["cnpj"], "12ABC34501DE35")
        FiscalCustomerData.objects.create(customer=self.customer, icms_status="NON_CONTRIBUTOR", **self.address)
        FiscalEquipmentData.objects.create(equipment=self.equipment, ncm="84672999", asset_value=5000)
        result = self.client.get(f"/api/fiscal/rentals/{self.quote.id}/export/")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.data["data_ready"])
        self.assertFalse(result.data["can_issue"])
        self.assertFalse(result.data["fiscal_document"])
        self.assertTrue(result.data["integration_pending"])
        self.assertEqual(result.data["equipment"][0]["fiscal"]["asset_value"], "5000.00")
        self.assertEqual(result.data["rental"]["commercial_totals"]["equipment"], "300.00")
        self.assertTrue(AuditLog.objects.filter(entity="FiscalCompany", action="FISCAL_DATA_UPDATED").exists())

    def test_rejects_invalid_codes_and_keeps_equipment_rental_values_separate(self):
        invalid = self.client.patch("/api/fiscal/company/", {"cnpj": "11.111.111/1111-11", "state": "XX"}, format="json")
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(FiscalCompany.objects.exists())
        endpoint = f"/api/fiscal/equipment/{self.equipment.id}/"
        self.assertEqual(self.client.patch(endpoint, {"ncm": "123", "asset_value": -1}, format="json").status_code, 400)
        valid = self.client.patch(endpoint, {"ncm": "84672999", "asset_value": "5000.00"}, format="json")
        self.assertEqual(valid.status_code, 200, valid.data)
        self.equipment.refresh_from_db()
        self.assertEqual(self.equipment.daily_rate, 100)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.address, "Endereço legado preservado")
