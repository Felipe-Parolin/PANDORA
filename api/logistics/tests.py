from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from customers.models import Customer
from rentals.models import RentalInspection, RentalItem, RentalQuote

from .models import TransportTask, Vehicle


class TransportFlowTests(TestCase):
    def setUp(self):
        self.sales = User.objects.create_user("sales-transport@example.com", "test-password", full_name="Vendedora", role=User.Role.SALES)
        self.technician = User.objects.create_user("tech-transport@example.com", "test-password", full_name="Técnico", role=User.Role.MAINTENANCE)
        self.customer = Customer.objects.create(person_type="PF", name="Cliente", document="12345678909", phone="19999999999")
        category = EquipmentCategory.objects.create(name="Categoria", default_daily_rate=Decimal("100"))
        self.equipment = Equipment.objects.create(category=category, name="Equipamento", brand="Marca", model="M1", serial_number="SER-TR", internal_code="EQ-TR", daily_rate=Decimal("100"))
        self.vehicle = Vehicle.objects.create(plate="ABC1D23", brand="Fiat", model="Strada", capacity_kg=700)
        self.quote = RentalQuote.objects.create(
            customer=self.customer, start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=2),
            status=RentalQuote.Status.SENT, conditions="Entrega e coleta agendadas.", created_by=self.sales,
            delivery_transport_required=True, return_transport_required=True,
            delivery_address="Rua A, 10, Leme/SP", return_address="Rua A, 10, Leme/SP",
            delivery_complement="Portão lateral", return_complement="Entrada dos fundos",
            transport_fee=Decimal("60"), discount=Decimal("10"),
        )
        RentalItem.objects.create(quote=self.quote, equipment=self.equipment, daily_rate=100, quantity_days=3)
        self.quote.recalculate()
        self.client = APIClient()
        self.client.force_authenticate(self.sales)

    def test_full_optional_transport_flow(self):
        self.assertEqual(self.quote.total, Decimal("350"))
        self.assertFalse(TransportTask.objects.filter(quote=self.quote).exists())
        response = self.client.post(f"/api/rental-quotes/{self.quote.pk}/reserve/")
        self.assertEqual(response.status_code, 200, response.data)
        outbound = TransportTask.objects.get(quote=self.quote, leg=TransportTask.Leg.DELIVERY)
        self.assertEqual(outbound.status, TransportTask.Status.PLANNED)
        self.assertEqual(outbound.complement, "Portão lateral")
        listed = self.client.get("/api/transport-tasks/")
        self.assertEqual(listed.status_code, 200, listed.data)
        tasks = listed.data["results"] if isinstance(listed.data, dict) else listed.data
        self.assertTrue(any(task["id"] == outbound.pk and task["complement"] == "Portão lateral" for task in tasks))
        self.assertEqual(self.client.post(f"/api/transport-tasks/{outbound.pk}/start/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/rental-quotes/{self.quote.pk}/deliver/").status_code, 400)

        inspection = RentalInspection.objects.get(quote=self.quote, inspection_type=RentalInspection.Type.PRE_RENTAL)
        checklist = [{**item, "status": "OK"} for item in inspection.checklist]
        self.client.force_authenticate(self.technician)
        response = self.client.patch(
            f"/api/rental-inspections/{inspection.pk}/",
            {"checklist": checklist, "result": RentalInspection.Result.APPROVED}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.post(f"/api/transport-tasks/{outbound.pk}/start/").status_code, 403)

        self.client.force_authenticate(self.sales)
        when = (timezone.now() + timedelta(hours=2)).isoformat()
        response = self.client.patch(
            f"/api/transport-tasks/{outbound.pk}/",
            {"vehicle": self.vehicle.pk, "driver": self.sales.pk, "scheduled_at": when}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.post(f"/api/transport-tasks/{outbound.pk}/start/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/rental-quotes/{self.quote.pk}/deliver/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/transport-tasks/{outbound.pk}/complete/").status_code, 200)
        response = self.client.post(f"/api/rental-quotes/{self.quote.pk}/deliver/")
        self.assertEqual(response.status_code, 200, response.data)

        inbound = TransportTask.objects.get(quote=self.quote, leg=TransportTask.Leg.RETURN)
        self.assertEqual(inbound.complement, "Entrada dos fundos")
        self.assertEqual(self.client.post(f"/api/rental-quotes/{self.quote.pk}/return/").status_code, 400)
        response = self.client.patch(
            f"/api/transport-tasks/{inbound.pk}/",
            {"vehicle": self.vehicle.pk, "driver": self.sales.pk, "scheduled_at": when}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.post(f"/api/transport-tasks/{inbound.pk}/start/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/transport-tasks/{inbound.pk}/complete/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/rental-quotes/{self.quote.pk}/return/").status_code, 200)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, RentalQuote.Status.RETURNED)

    def test_approval_without_delivery_does_not_create_trip(self):
        self.quote.delivery_transport_required = False
        self.quote.return_transport_required = False
        self.quote.transport_fee = Decimal("0")
        self.quote.save(update_fields=("delivery_transport_required", "return_transport_required", "transport_fee"))
        self.quote.recalculate()
        response = self.client.post(f"/api/rental-quotes/{self.quote.pk}/reserve/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(TransportTask.objects.filter(quote=self.quote).exists())

    def test_vehicle_validation_and_history(self):
        response = self.client.post("/api/vehicles/", {"plate": "invalid", "brand": "A", "model": "B"})
        self.assertEqual(response.status_code, 400)
        self.client.post(f"/api/rental-quotes/{self.quote.pk}/reserve/")
        response = self.client.delete(f"/api/vehicles/{self.vehicle.pk}/")
        self.assertEqual(response.status_code, 204)
        self.vehicle = Vehicle.objects.create(plate="DEF2G34", brand="Fiat", model="Strada")
        outbound = TransportTask.objects.get(quote=self.quote, leg=TransportTask.Leg.DELIVERY)
        self.client.patch(f"/api/transport-tasks/{outbound.pk}/", {"vehicle": self.vehicle.pk}, format="json")
        response = self.client.delete(f"/api/vehicles/{self.vehicle.pk}/")
        self.assertEqual(response.status_code, 409)
