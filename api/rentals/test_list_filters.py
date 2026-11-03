from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from assets.models import Equipment, EquipmentCategory


class EquipmentSearchOrderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("filters@example.invalid", "test-password", full_name="Teste", role=User.Role.ADMIN)
        cls.category = EquipmentCategory.objects.create(name="Categoria A")
        cls.other_category = EquipmentCategory.objects.create(name="Categoria B")
        Equipment.objects.bulk_create([
            Equipment(category=cls.category if i <= 40 else cls.other_category, name=f"Equipamento {i:02d}", brand="Alpha" if i % 2 else "Beta", model="Modelo", serial_number=f"TEST-S-{i}", internal_code=f"TEST-{i:03d}", daily_rate=Decimal(i))
            for i in range(1, 54)
        ])

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.params = {"start": timezone.localdate().isoformat(), "end": (timezone.localdate() + timedelta(days=1)).isoformat(), "page_size": 10}

    def availability(self, **params):
        return self.client.get("/api/rental-quotes/availability/", {**self.params, **params})

    def test_rate_sort_is_global_before_availability_pagination(self):
        first = self.availability(ordering="-daily_rate")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["count"], 53)
        self.assertEqual(first.data["next_page"], 2)
        self.assertEqual([Decimal(row["equipment"]["daily_rate"]) for row in first.data["available"]], list(map(Decimal, range(53, 43, -1))))
        second = self.availability(ordering="-daily_rate", page=2)
        self.assertEqual([Decimal(row["equipment"]["daily_rate"]) for row in second.data["available"]], list(map(Decimal, range(43, 33, -1))))

    def test_brand_rate_bounds_and_category_combine_before_count(self):
        result = self.availability(brand="bEtA", min_daily_rate="20", max_daily_rate="30", category=self.category.pk, ordering="daily_rate")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 6)
        self.assertEqual([Decimal(row["equipment"]["daily_rate"]) for row in result.data["available"]], list(map(Decimal, [20, 22, 24, 26, 28, 30])))
        self.assertIsNone(result.data["next_page"])

    def test_name_search_and_reverse_order_are_consistent(self):
        result = self.availability(search="Equipamento 5", ordering="-name")
        self.assertEqual(result.status_code, 200)
        self.assertEqual([row["equipment"]["name"] for row in result.data["available"]], ["Equipamento 53", "Equipamento 52", "Equipamento 51", "Equipamento 50"])

    def test_rejects_unknown_order_and_invalid_rate_ranges(self):
        for params in [
            {"ordering": "__class__"}, {"min_daily_rate": "-1"}, {"max_daily_rate": "NaN"},
            {"min_daily_rate": "Infinity"}, {"min_daily_rate": "texto"}, {"min_daily_rate": "1e10000"},
            {"min_daily_rate": "30", "max_daily_rate": "20"},
        ]:
            with self.subTest(params=params):
                self.assertEqual(self.availability(**params).status_code, 400)

    def test_equipment_catalog_accepts_rate_order_across_all_records(self):
        result = self.client.get("/api/equipment/", {"ordering": "-daily_rate"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 53)
        self.assertEqual(Decimal(result.data["results"][0]["daily_rate"]), Decimal(53))
        self.assertTrue(result.data["next"])

    def test_selection_check_can_still_request_specific_equipment(self):
        ids = list(Equipment.objects.order_by("id").values_list("id", flat=True)[:2])
        result = self.availability(equipment_ids=",".join(map(str, ids)))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 2)
        self.assertEqual({row["equipment"]["id"] for row in result.data["available"]}, set(ids))
