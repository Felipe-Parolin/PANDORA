from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from customers.models import Customer
from maintenance.models import MaintenancePlan, ServiceOrder
from rentals.models import RentalInspection, RentalItem, RentalQuote
from rentals.serializers import RentalQuoteSerializer
from rentals.services import availability_reason


class RentalRulesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sales@example.com", "strong-password", full_name="Vendas", role=User.Role.SALES)
        self.customer = Customer.objects.create(person_type="PF", name="Cliente", document="12345678909", phone="19999999999")
        self.category = EquipmentCategory.objects.create(name="Categoria", default_daily_rate=100)
        self.equipment = Equipment.objects.create(category=self.category, name="Equipamento", brand="Marca", model="M1", serial_number="SER-2", internal_code="EQ-T2", daily_rate=Decimal("100"))
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_quote(self, status=RentalQuote.Status.SENT):
        quote = RentalQuote.objects.create(
            customer=self.customer,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=2),
            status=status,
            conditions="Retirada no balcão.",
            created_by=self.user,
        )
        RentalItem.objects.create(quote=quote, equipment=self.equipment, daily_rate=100, quantity_days=3, total=300)
        return quote

    def test_quote_recalculates_total(self):
        quote = RentalQuote.objects.create(customer=self.customer, start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=2), created_by=self.user)
        RentalItem.objects.create(quote=quote, equipment=self.equipment, daily_rate=100, quantity_days=3, total=0)
        quote.recalculate()
        self.assertEqual(quote.total, Decimal("300"))

    def test_approved_quote_blocks_overlap(self):
        quote = RentalQuote.objects.create(customer=self.customer, start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=2), status=RentalQuote.Status.APPROVED, created_by=self.user)
        RentalItem.objects.create(quote=quote, equipment=self.equipment, daily_rate=100, quantity_days=3, total=300)
        self.assertIsNotNone(availability_reason(self.equipment, timezone.localdate() + timedelta(days=1), timezone.localdate() + timedelta(days=4)))
        self.assertIsNone(availability_reason(self.equipment, quote.start_date, quote.end_date, ignore_quote=quote))

    def test_serializer_rejects_duplicate_equipment(self):
        payload = {
            "customer": self.customer.pk,
            "start_date": timezone.localdate(),
            "end_date": timezone.localdate() + timedelta(days=1),
            "items": [
                {"equipment_id": self.equipment.pk, "daily_rate": "100.00", "quantity_days": 99},
                {"equipment_id": self.equipment.pk, "daily_rate": "100.00", "quantity_days": 99},
            ],
        }
        serializer = RentalQuoteSerializer(data=payload, context={"request": SimpleNamespace(user=self.user)})
        self.assertFalse(serializer.is_valid())
        self.assertIn("items", serializer.errors)

    def test_server_calculates_quantity_days(self):
        payload = {
            "customer": self.customer.pk,
            "start_date": timezone.localdate(),
            "end_date": timezone.localdate() + timedelta(days=2),
            "items": [{"equipment_id": self.equipment.pk, "daily_rate": "100.00", "quantity_days": 99}],
        }
        serializer = RentalQuoteSerializer(data=payload, context={"request": SimpleNamespace(user=self.user)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        quote = serializer.save()
        self.assertEqual(quote.items.get().quantity_days, 3)

    def test_reservation_creates_pre_rental_inspection_and_responsible(self):
        self.category.pre_rental_checklist = ["Trava da categoria", "Teste específico"]
        self.category.save(update_fields=("pre_rental_checklist",))
        quote = self.create_quote()
        response = self.client.post(f"/api/rental-quotes/{quote.pk}/reserve/")
        self.assertEqual(response.status_code, 200, response.data)
        quote.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(quote.status, RentalQuote.Status.APPROVED)
        self.assertEqual(quote.reserved_by, self.user)
        self.assertEqual(self.equipment.status, Equipment.Status.RESERVED)
        inspection = quote.inspections.get(inspection_type=RentalInspection.Type.PRE_RENTAL)
        self.assertEqual([item["label"] for item in inspection.checklist], self.category.pre_rental_checklist)

    def test_critical_usage_maintenance_blocks_availability(self):
        self.equipment.current_usage_hours = 120
        self.equipment.save(update_fields=("current_usage_hours",))
        MaintenancePlan.objects.create(
            equipment=self.equipment,
            name="Revisão crítica",
            maintenance_type=MaintenancePlan.Type.PREVENTIVE,
            usage_limit=100,
            last_service_usage_hours=0,
            criticality=MaintenancePlan.Criticality.CRITICAL,
        )
        reason = availability_reason(self.equipment, timezone.localdate(), timezone.localdate() + timedelta(days=1))
        self.assertIn("horas de uso", reason)

    def test_delivery_requires_approved_pre_rental_inspection(self):
        quote = self.create_quote()
        self.client.post(f"/api/rental-quotes/{quote.pk}/reserve/")
        blocked = self.client.post(f"/api/rental-quotes/{quote.pk}/deliver/", {"conditions": "Sem ressalvas."}, format="json")
        self.assertEqual(blocked.status_code, 400)
        inspection = quote.inspections.get(inspection_type=RentalInspection.Type.PRE_RENTAL)
        checklist = [{**item, "status": "OK"} for item in inspection.checklist]
        response = self.client.patch(
            f"/api/rental-inspections/{inspection.pk}/",
            {"checklist": checklist, "result": RentalInspection.Result.APPROVED, "condition": RentalInspection.Condition.GOOD},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        delivered = self.client.post(f"/api/rental-quotes/{quote.pk}/deliver/", {"conditions": "Sem ressalvas."}, format="json")
        self.assertEqual(delivered.status_code, 200, delivered.data)
        quote.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(quote.status, RentalQuote.Status.ACTIVE)
        self.assertEqual(self.equipment.status, Equipment.Status.RENTED)

    def test_extension_rechecks_conflicts(self):
        quote = self.create_quote(status=RentalQuote.Status.ACTIVE)
        other = RentalQuote.objects.create(
            customer=self.customer,
            start_date=quote.end_date + timedelta(days=1),
            end_date=quote.end_date + timedelta(days=3),
            status=RentalQuote.Status.APPROVED,
            conditions="Reserva concorrente",
            created_by=self.user,
        )
        RentalItem.objects.create(quote=other, equipment=self.equipment, daily_rate=100, quantity_days=3, total=300)
        response = self.client.post(
            f"/api/rental-quotes/{quote.pk}/extend/",
            {"new_end_date": (quote.end_date + timedelta(days=2)).isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("availability", response.data)

    def test_return_inspection_routes_damage_to_maintenance(self):
        quote = self.create_quote(status=RentalQuote.Status.ACTIVE)
        returned = self.client.post(f"/api/rental-quotes/{quote.pk}/return/", {"conditions": "Equipamento recebido."}, format="json")
        self.assertEqual(returned.status_code, 200, returned.data)
        inspection = quote.inspections.get(inspection_type=RentalInspection.Type.RETURN)
        checklist = [{**item, "status": "WARNING"} for item in inspection.checklist]
        inspected = self.client.patch(
            f"/api/rental-inspections/{inspection.pk}/",
            {
                "checklist": checklist,
                "result": RentalInspection.Result.APPROVED_WITH_NOTES,
                "condition": RentalInspection.Condition.DAMAGED,
                "observations": "Proteção lateral amassada.",
            },
            format="json",
        )
        self.assertEqual(inspected.status_code, 200, inspected.data)
        finalized = self.client.post(f"/api/rental-quotes/{quote.pk}/finalize-return/")
        self.assertEqual(finalized.status_code, 200, finalized.data)
        quote.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(quote.status, RentalQuote.Status.COMPLETED)
        self.assertEqual(self.equipment.status, Equipment.Status.MAINTENANCE)
        self.assertTrue(ServiceOrder.objects.filter(rental_inspection=inspection).exists())
