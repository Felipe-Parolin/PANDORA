from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from customers.models import Customer
from logistics.models import TransportTask
from logistics.services import ensure_transport_task
from .documents import snapshot_for
from .models import RentalDocument, RentalItem, RentalQuote


class RentalSchedulingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("schedule@example.invalid", "test", full_name="Operador", role="SALES")
        customer = Customer.objects.create(person_type="PF", name="Cliente", document="12345678909", phone="19999999999")
        category = EquipmentCategory.objects.create(name="Agendamento")
        cls.equipment = Equipment.objects.create(category=category, name="Equipamento", brand="Marca", model="Modelo", serial_number="SCHEDULE-1", internal_code="SCHEDULE-1", daily_rate=100)
        cls.quote = RentalQuote.objects.create(customer=customer, start_date=timezone.localdate(), end_date=timezone.localdate()+timedelta(days=2), conditions="Retirada combinada", created_by=cls.user)
        RentalItem.objects.create(quote=cls.quote, equipment=cls.equipment, daily_rate=100, quantity_days=3, total=300)
        cls.quote.recalculate()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/rental-quotes/{self.quote.pk}/"

    def test_editing_quote_accepts_null_or_blank_optional_datetimes(self):
        for value in (None, ""):
            response = self.client.patch(self.url, {"requested_delivery_at": value, "requested_return_at": value, "notes": "Editado"}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertIsNone(response.data["requested_delivery_at"])
            self.assertIsNone(response.data["requested_return_at"])

    def test_round_trip_preserves_datetime_instant_and_current_items(self):
        delivery = timezone.now().replace(second=0, microsecond=0)
        returning = delivery + timedelta(days=2)
        response = self.client.patch(self.url, {"requested_delivery_at": delivery.isoformat(), "requested_return_at": returning.isoformat()}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.patch(self.url, {"requested_delivery_at": response.data["requested_delivery_at"], "requested_return_at": response.data["requested_return_at"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.requested_delivery_at, delivery)
        self.assertEqual(self.quote.requested_return_at, returning)
        self.assertEqual(self.quote.items.count(), 1)

    def test_return_before_delivery_and_invalid_datetime_are_rejected(self):
        delivery = timezone.now()
        response = self.client.patch(self.url, {"requested_delivery_at": delivery.isoformat(), "requested_return_at": (delivery-timedelta(hours=1)).isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("requested_return_at", response.data)
        self.assertEqual(self.client.patch(self.url, {"requested_delivery_at": "inválido"}, format="json").status_code, 400)

    def test_return_transport_uses_agreed_time_and_document_snapshot_preserves_it(self):
        self.quote.status = RentalQuote.Status.ACTIVE
        self.quote.items.update(stage="DELIVERED")
        self.quote.return_transport_required = True
        self.quote.return_address = "Endereço de coleta"
        self.quote.requested_return_at = timezone.now()+timedelta(days=2)
        self.quote.save()
        task = ensure_transport_task(self.quote, TransportTask.Leg.RETURN, self.user)
        self.assertEqual(task.scheduled_at, self.quote.requested_return_at)
        snapshot = snapshot_for(self.quote, RentalDocument.Kind.QUOTE)
        self.assertEqual(snapshot["requested_return_at"], self.quote.requested_return_at.isoformat())

    def test_selected_availability_is_independent_of_catalog_category(self):
        Equipment.objects.create(category=self.equipment.category, name="Outro", brand="Marca", model="Modelo", serial_number="SCHEDULE-2", internal_code="SCHEDULE-2", daily_rate=100)
        params = {"start": self.quote.start_date.isoformat(), "end": self.quote.end_date.isoformat(), "ignore_quote": self.quote.pk, "equipment_ids": str(self.equipment.pk)}
        response = self.client.get("/api/rental-quotes/availability/", params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        found = response.data["available"] + response.data["blocked"]
        self.assertEqual([item["equipment"]["id"] for item in found], [self.equipment.pk])
        params["equipment_ids"] = "inválido"
        self.assertEqual(self.client.get("/api/rental-quotes/availability/", params).status_code, 400)
