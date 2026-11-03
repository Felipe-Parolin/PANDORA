import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from assets.models import Equipment, EquipmentCategory
from logistics.geo import geocode_precise_address, origin_point
from logistics.models import Vehicle
from logistics.routing import road_route
from rentals.freight import estimate_freight, freight_origin


ORIGIN = (-22.1757125, -47.3820152)
DESTINATION = (-22.19, -47.40)
ADDRESS = "Rua de teste, 120, Leme/SP"


@override_settings(
    FREIGHT_ORIGIN_LATITUDE=str(ORIGIN[0]), FREIGHT_ORIGIN_LONGITUDE=str(ORIGIN[1]),
    FREIGHT_ORIGIN_LABEL="Depósito confirmado", FREIGHT_RATE_PER_KM=Decimal("3"),
    FREIGHT_MINIMUM_PER_LEG=Decimal("25"), FREIGHT_OPERATIONAL_COST_PER_TRIP=Decimal("0"),
    FREIGHT_EXTRA_FEE=Decimal("0"), FREIGHT_CITY_SURCHARGES={},
)
class RoadFreightTests(SimpleTestCase):
    def setUp(self):
        self.point = patch("logistics.geo.geocode_precise_address", return_value=DESTINATION).start()
        self.route = patch("logistics.routing.road_route", return_value={"distance_m": 10123, "duration_seconds": 1000}).start()
        self.addCleanup(patch.stopall)

    def test_charges_unrounded_road_distance_and_keeps_return_direction(self):
        result = estimate_freight({"city": "Leme", "state": "SP"}, address=ADDRESS)
        self.assertEqual(result["fee"], "30.37")
        self.assertEqual(result["distance_km"], "10.1")
        self.assertEqual(result["duration_minutes"], 17)
        self.route.assert_called_once_with(ORIGIN, DESTINATION)
        self.route.reset_mock()
        self.route.return_value = {"distance_m": 12000, "duration_seconds": 1100}
        returning = estimate_freight({}, address=ADDRESS, leg="RETURN")
        self.route.assert_called_once_with(DESTINATION, ORIGIN)
        self.assertEqual(returning["fee"], "36.00")

    def test_local_route_uses_minimum(self):
        self.route.return_value = {"distance_m": 1500, "duration_seconds": 100}
        self.assertEqual(estimate_freight({}, address=ADDRESS)["fee"], "25.00")

    def test_street_point_requires_confirmation_before_routing_or_pricing(self):
        self.point.return_value = None
        destination = {"street": "Rua de teste", "cep": "13614032", "city": "Leme", "state": "SP", "latitude": DESTINATION[0], "longitude": DESTINATION[1]}
        preview = estimate_freight(destination, address=ADDRESS, allow_approximate=False)
        self.assertIsNone(preview["fee"])
        self.assertTrue(preview["requires_location_confirmation"])
        self.route.assert_not_called()
        accepted = estimate_freight(destination, address=ADDRESS, allow_approximate=True, leg="RETURN")
        self.assertEqual(accepted["fee"], "30.37")
        self.assertEqual(accepted["destination_precision"], "CEP_STREET")
        self.assertTrue(accepted["approximate_destination"])
        self.route.assert_called_once_with(DESTINATION, ORIGIN)

    def test_approximation_rejects_wrong_street_city_centroid_and_invalid_coordinates(self):
        self.point.return_value = None
        for street, latitude in (("Outra rua", DESTINATION[0]), ("", DESTINATION[0]), ("Rua de teste", float("nan")), ("Rua de teste", 0)):
            data = {"street": street, "latitude": latitude, "longitude": DESTINATION[1]}
            # Latitude zero ainda fica no Brasil; o caso usa longitude fora do país.
            if latitude == 0: data["longitude"] = 0
            self.assertIsNone(estimate_freight(data, address=ADDRESS, allow_approximate=True)["fee"])
        self.route.assert_not_called()

    @override_settings(FREIGHT_OPERATIONAL_COST_PER_TRIP=Decimal("10"), FREIGHT_EXTRA_FEE=Decimal("5"), FREIGHT_CITY_SURCHARGES={"leme/SP": "2"})
    def test_configured_components_are_preserved(self):
        result = estimate_freight({"city": "Leme", "state": "SP"}, address=ADDRESS)
        self.assertEqual(result["fee"], "47.37")
        self.assertEqual(result["breakdown"]["city_surcharge_per_trip"], "2.00")

    def test_missing_address_never_routes_to_postal_centroid(self):
        self.assertIsNone(estimate_freight({"latitude": -22.18, "longitude": -47.38})["fee"])
        self.point.assert_not_called()
        self.route.assert_not_called()

    def test_unlocated_number_or_route_failure_has_no_invented_fee(self):
        self.point.return_value = None
        self.assertIsNone(estimate_freight({}, address=ADDRESS)["fee"])
        self.route.assert_not_called()
        self.point.return_value = DESTINATION
        self.route.return_value = None
        self.assertIsNone(estimate_freight({}, address=ADDRESS)["fee"])

    def test_confirmed_origin_matches_map_and_needs_no_geocoding(self):
        self.assertEqual(freight_origin(), ORIGIN)
        point = origin_point()
        self.assertEqual((point["latitude"], point["longitude"]), ORIGIN)
        self.assertFalse(point["provisional"])
        self.point.assert_not_called()


@override_settings(FREIGHT_ROUTING_URL="https://routing.example.invalid")
class RouteProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("logistics.routing.urlopen")
    def test_order_longitude_first_and_route_response_cache(self, mocked):
        response = MagicMock()
        response.read.return_value = json.dumps({"code": "Ok", "routes": [{"distance": 2500, "duration": 300}], "waypoints": [{"distance": 4}, {"distance": 7}]}).encode()
        mocked.return_value.__enter__.return_value = response
        self.assertEqual(road_route(ORIGIN, DESTINATION), {"distance_m": 2500, "duration_seconds": 300})
        self.assertEqual(road_route(ORIGIN, DESTINATION)["distance_m"], 2500)
        self.assertEqual(mocked.call_count, 1)
        self.assertIn("-47.3820152,-22.1757125;-47.4000000,-22.1900000", mocked.call_args.args[0].full_url)
        road_route(DESTINATION, ORIGIN)
        self.assertEqual(mocked.call_count, 2)

    @patch("logistics.routing.urlopen")
    def test_rejects_missing_invalid_and_distant_road_results(self, mocked):
        for data in [
            {"code": "NoRoute"}, [], {},
            {"code": "Ok", "routes": []},
            {"code": "Ok", "routes": [{"distance": -1, "duration": 1}], "waypoints": [{"distance": 0}, {"distance": 0}]},
            {"code": "Ok", "routes": [{"distance": float("nan"), "duration": 1}], "waypoints": [{"distance": 0}, {"distance": 0}]},
            {"code": "Ok", "routes": [{"distance": 1, "duration": 1}], "waypoints": [{"distance": 0}, {"distance": 501}]},
        ]:
            with self.subTest(data=data):
                cache.clear()
                mocked.return_value.__enter__.return_value.read.return_value = json.dumps(data).encode()
                self.assertIsNone(road_route(ORIGIN, DESTINATION))

    @patch("logistics.routing.urlopen", side_effect=TimeoutError)
    def test_outage_returns_none_and_short_failure_cache(self, mocked):
        self.assertIsNone(road_route(ORIGIN, DESTINATION))
        self.assertIsNone(road_route(ORIGIN, DESTINATION))
        mocked.assert_called_once()

    @override_settings(FREIGHT_ROUTING_URL="")
    @patch("logistics.routing.urlopen")
    def test_unconfigured_provider_never_makes_external_request(self, mocked):
        self.assertIsNone(road_route(ORIGIN, DESTINATION))
        mocked.assert_not_called()


class PreciseGeocodingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("logistics.geo._throttle")
    @patch("logistics.geo.urlopen")
    def test_street_result_is_not_accepted_as_house(self, mocked, throttle):
        mocked.return_value.__enter__.return_value.read.return_value = json.dumps([{"lat": "-22.19", "lon": "-47.40", "address": {"road": "Rua de teste"}}]).encode()
        self.assertIsNone(geocode_precise_address(ADDRESS))
        self.assertIsNone(geocode_precise_address(ADDRESS))
        mocked.assert_called_once()

    @patch("logistics.geo._throttle")
    @patch("logistics.geo.urlopen")
    def test_exact_number_is_cached_but_different_number_is_rejected(self, mocked, throttle):
        mocked.return_value.__enter__.return_value.read.return_value = json.dumps([{"lat": "-22.19", "lon": "-47.40", "address": {"house_number": "120"}}]).encode()
        self.assertEqual(geocode_precise_address(ADDRESS), DESTINATION)
        self.assertEqual(geocode_precise_address(ADDRESS), DESTINATION)
        mocked.assert_called_once()
        self.assertIsNone(geocode_precise_address("Rua de teste, 121, Leme/SP"))


class FreightEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("freight@example.invalid", "test-password", full_name="Teste", role=User.Role.SALES)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("rentals.views.estimate_freight", return_value={"fee": "36.00"})
    @patch("rentals.views.lookup_cep", return_value={"cep": "13614032", "city": "Leme", "state": "SP"})
    def test_passes_address_number_equipment_and_return_leg(self, cep, freight):
        response = self.client.get("/api/rental-quotes/lookup-address/", {"cep": "13614032", "address": ADDRESS, "leg": "RETURN", "equipment_ids": "1,2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["estimate"]["fee"], "36.00")
        freight.assert_called_once_with(cep.return_value, ["1", "2"], address=ADDRESS, leg="RETURN", allow_approximate=True)

    @patch("rentals.views.lookup_cep", return_value={})
    def test_rejects_invalid_leg_and_oversized_address(self, cep):
        for params in ({"leg": "unknown"}, {"address": "x" * 256}):
            self.assertEqual(self.client.get("/api/rental-quotes/lookup-address/", {"cep": "13614032", **params}).status_code, 400)
        cep.assert_not_called()

    @patch("rentals.views.lookup_cep")
    def test_requires_sales_permission_before_consulting_provider(self, cep):
        self.user.role = User.Role.MAINTENANCE
        self.user.save()
        self.assertEqual(self.client.get("/api/rental-quotes/lookup-address/", {"cep": "13614032"}).status_code, 403)
        cep.assert_not_called()

    @override_settings(FREIGHT_ORIGIN_LATITUDE=str(ORIGIN[0]), FREIGHT_ORIGIN_LONGITUDE=str(ORIGIN[1]), FREIGHT_RATE_PER_KM=Decimal("3"), FREIGHT_MINIMUM_PER_LEG=Decimal("25"), FREIGHT_OPERATIONAL_COST_PER_TRIP=Decimal("0"), FREIGHT_EXTRA_FEE=Decimal("0"), FREIGHT_CITY_SURCHARGES={}, FREIGHT_ITEMS_PER_TRIP=3)
    @patch("logistics.geo.geocode_precise_address", return_value=DESTINATION)
    @patch("logistics.routing.road_route", return_value={"distance_m": 10000, "duration_seconds": 1000})
    def test_existing_load_trip_pricing_is_preserved(self, route, point):
        category = EquipmentCategory.objects.create(name="Teste")
        equipment = [Equipment.objects.create(category=category, name=f"Item {i}", brand="Marca", model="M", serial_number=f"S{i}", internal_code=f"EQ{i}", daily_rate=100, estimated_weight_kg=100) for i in range(4)]
        Vehicle.objects.create(plate="ABC1D23", brand="Marca", model="Modelo", capacity_kg=200)
        result = estimate_freight({}, [item.id for item in equipment], address=ADDRESS)
        self.assertEqual(result["trip_count"], 2)
        self.assertEqual(result["fee"], "60.00")
