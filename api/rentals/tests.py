from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import json

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from customers.models import Customer
from maintenance.models import MaintenancePlan, ServiceOrder
from rentals.models import RentalInspection, RentalItem, RentalQuote
from rentals.serializers import RentalQuoteSerializer
from rentals.services import availability_reason
from rentals.freight import estimate_freight, lookup_cep


class RentalRulesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sales@example.com", "strong-password", full_name="Vendas", role=User.Role.SALES)
        self.technician = User.objects.create_user("tech@example.com", "strong-password", full_name="Técnico", role=User.Role.MAINTENANCE)
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

    def test_percentage_discount_includes_transport_and_is_recalculated(self):
        payload = {
            "customer": self.customer.pk,
            "start_date": timezone.localdate(),
            "end_date": timezone.localdate() + timedelta(days=1),
            "items": [{"equipment_id": self.equipment.pk, "daily_rate": "100.00", "quantity_days": 2}],
            "delivery_transport_required": True,
            "delivery_address": "Rua A, 10, Leme/SP",
            "delivery_cep": "13610050",
            "transport_fee": "20.00",
            "discount_percent": "10.00",
        }
        serializer = RentalQuoteSerializer(data=payload, context={"request": SimpleNamespace(user=self.user)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        quote = serializer.save()
        self.assertEqual(quote.discount, Decimal("22.00"))
        self.assertEqual(quote.total, Decimal("198.00"))
        quote.transport_fee = Decimal("40.00")
        quote.recalculate()
        self.assertEqual(quote.discount, Decimal("24.00"))
        self.assertEqual(quote.total, Decimal("216.00"))

    def test_percentage_and_cep_validation(self):
        payload = {
            "customer": self.customer.pk,
            "start_date": timezone.localdate(),
            "end_date": timezone.localdate(),
            "items": [{"equipment_id": self.equipment.pk, "daily_rate": "100.00", "quantity_days": 1}],
            "discount_percent": "101.00",
            "delivery_cep": "123",
        }
        serializer = RentalQuoteSerializer(data=payload, context={"request": SimpleNamespace(user=self.user)})
        self.assertFalse(serializer.is_valid())
        self.assertIn("delivery_cep", serializer.errors)
        payload["delivery_cep"] = "13610050"
        serializer = RentalQuoteSerializer(data=payload, context={"request": SimpleNamespace(user=self.user)})
        self.assertFalse(serializer.is_valid())
        self.assertIn("discount_percent", serializer.errors)

    @override_settings(FREIGHT_ORIGIN_CEP="13610050", FREIGHT_ORIGIN_LABEL="Origem de teste", FREIGHT_ORIGIN_PROVISIONAL=False,
                       FREIGHT_MINIMUM_PER_LEG=Decimal("25"), FREIGHT_RATE_PER_KM=Decimal("3"), FREIGHT_ROAD_FACTOR=Decimal("1.3"))
    @patch("rentals.freight.lookup_cep")
    def test_freight_estimate_has_minimum_and_missing_coordinate_fallback(self, mocked_lookup):
        mocked_lookup.return_value = {"latitude": -22.18556, "longitude": -47.39028}
        destination = {"latitude": -22.18556, "longitude": -47.39028}
        estimate = estimate_freight(destination)
        self.assertEqual(estimate["fee"], "25.00")
        self.assertEqual(estimate["distance_km"], "0.0")
        self.assertEqual(estimate["origin_label"], "Origem de teste")
        self.assertIsNone(estimate_freight({"latitude": None, "longitude": None})["fee"])

    @patch("rentals.views.estimate_freight", return_value={"fee": "25.00", "distance_km": "0.0"})
    @patch("rentals.views.lookup_cep", return_value={"cep": "13610050", "street": "Rua General Osório", "city": "Leme", "state": "SP"})
    def test_address_lookup_endpoint(self, mocked_lookup, mocked_estimate):
        response = self.client.get("/api/rental-quotes/lookup-address/?cep=13610050")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["street"], "Rua General Osório")
        self.assertEqual(response.data["estimate"]["fee"], "25.00")
        mocked_lookup.assert_called_once_with("13610050")

    @patch("rentals.freight.urlopen")
    def test_cep_lookup_normalizes_and_caches_provider_result(self, mocked_urlopen):
        cache.delete("pandora:cep-v2:13610050")
        response = MagicMock()
        response.read.return_value = json.dumps({
            "cep": "13610-050", "street": "Rua General Osório", "neighborhood": "Centro",
            "city": "Leme", "state": "SP",
            "location": {"coordinates": {"latitude": "-22.18556", "longitude": "-47.39028"}},
        }).encode()
        mocked_urlopen.return_value.__enter__.return_value = response
        found = lookup_cep("13610-050")
        self.assertEqual(found["cep"], "13610050")
        self.assertEqual(found["latitude"], -22.18556)
        self.assertEqual(lookup_cep("13610050"), found)
        mocked_urlopen.assert_called_once()

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
        order = ServiceOrder.objects.get(rental_inspection=inspection)
        self.assertEqual(order.maintenance_type, ServiceOrder.Type.PRE_RENTAL)
        self.assertEqual(order.status, ServiceOrder.Status.OPEN)
        self.assertEqual(order.opened_by, self.user)
        self.assertIsNone(availability_reason(self.equipment, quote.start_date, quote.end_date, ignore_quote=quote))

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
        sales_attempt = self.client.patch(
            f"/api/rental-inspections/{inspection.pk}/",
            {"checklist": checklist, "result": RentalInspection.Result.APPROVED},
            format="json",
        )
        self.assertEqual(sales_attempt.status_code, 403)
        self.client.force_authenticate(self.technician)
        response = self.client.patch(
            f"/api/rental-inspections/{inspection.pk}/",
            {"checklist": checklist, "result": RentalInspection.Result.APPROVED, "condition": RentalInspection.Condition.GOOD},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order = ServiceOrder.objects.get(rental_inspection=inspection)
        self.assertEqual(order.status, ServiceOrder.Status.COMPLETED)
        self.assertTrue(order.released)
        self.assertEqual(order.technician, self.technician)
        self.client.force_authenticate(self.user)
        delivered = self.client.post(f"/api/rental-quotes/{quote.pk}/deliver/", {"conditions": "Sem ressalvas."}, format="json")
        self.assertEqual(delivered.status_code, 200, delivered.data)
        quote.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(quote.status, RentalQuote.Status.ACTIVE)
        self.assertEqual(self.equipment.status, Equipment.Status.RENTED)

    def test_blocked_pre_rental_inspection_keeps_order_open_and_prevents_delivery(self):
        quote = self.create_quote()
        self.client.post(f"/api/rental-quotes/{quote.pk}/reserve/")
        inspection = quote.inspections.get(inspection_type=RentalInspection.Type.PRE_RENTAL)
        self.client.force_authenticate(self.technician)
        response = self.client.patch(
            f"/api/rental-inspections/{inspection.pk}/",
            {
                "checklist": [{**item, "status": "FAIL"} for item in inspection.checklist],
                "result": RentalInspection.Result.BLOCKED,
                "condition": RentalInspection.Condition.CRITICAL,
                "observations": "Falha no freio.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        order = ServiceOrder.objects.get(rental_inspection=inspection)
        self.assertEqual(order.status, ServiceOrder.Status.IN_PROGRESS)
        self.assertFalse(order.released)
        self.equipment.refresh_from_db()
        self.assertEqual(self.equipment.status, Equipment.Status.MAINTENANCE)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(f"/api/rental-quotes/{quote.pk}/deliver/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/rental-quotes/{quote.pk}/cancel/", {"reason": "Falha crítica."}).status_code, 200)
        self.client.force_authenticate(self.technician)
        repaired = self.client.patch(
            f"/api/service-orders/{order.pk}/",
            {"status": "COMPLETED", "final_tests": "Freio reparado e testado.", "released": True},
            format="json",
        )
        self.assertEqual(repaired.status_code, 200, repaired.data)
        self.equipment.refresh_from_db()
        self.assertEqual(self.equipment.status, Equipment.Status.AVAILABLE)

    def test_cancel_reservation_closes_pending_inspection_order(self):
        quote = self.create_quote()
        self.client.post(f"/api/rental-quotes/{quote.pk}/reserve/")
        inspection = quote.inspections.get(inspection_type=RentalInspection.Type.PRE_RENTAL)
        response = self.client.post(f"/api/rental-quotes/{quote.pk}/cancel/", {"reason": "Cliente desistiu."})
        self.assertEqual(response.status_code, 200, response.data)
        order = ServiceOrder.objects.get(rental_inspection=inspection)
        self.assertEqual(order.status, ServiceOrder.Status.CANCELLED)
        self.equipment.refresh_from_db()
        self.assertEqual(self.equipment.status, Equipment.Status.AVAILABLE)

    def test_linked_order_cannot_be_closed_or_deleted_outside_inspection(self):
        quote = self.create_quote()
        self.client.post(f"/api/rental-quotes/{quote.pk}/reserve/")
        order = ServiceOrder.objects.get(rental_inspection__quote=quote)
        self.client.force_authenticate(self.technician)
        assigned = self.client.patch(
            f"/api/service-orders/{order.pk}/",
            {"status": "IN_PROGRESS", "technician": self.technician.pk},
            format="json",
        )
        self.assertEqual(assigned.status_code, 200, assigned.data)
        self.equipment.refresh_from_db()
        self.assertEqual(self.equipment.status, Equipment.Status.RESERVED)
        response = self.client.patch(f"/api/service-orders/{order.pk}/", {"status": "COMPLETED"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.delete(f"/api/service-orders/{order.pk}/").status_code, 409)

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
