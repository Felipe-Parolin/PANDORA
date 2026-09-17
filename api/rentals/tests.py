from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from customers.models import Customer
from rentals.models import RentalItem, RentalQuote
from rentals.serializers import RentalQuoteSerializer
from rentals.services import availability_reason


class RentalRulesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sales@example.com", "strong-password", full_name="Vendas", role=User.Role.SALES)
        self.customer = Customer.objects.create(person_type="PF", name="Cliente", document="12345678909", phone="19999999999")
        category = EquipmentCategory.objects.create(name="Categoria", default_daily_rate=100)
        self.equipment = Equipment.objects.create(category=category, name="Equipamento", brand="Marca", model="M1", serial_number="SER-2", internal_code="EQ-T2", daily_rate=Decimal("100"))

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
