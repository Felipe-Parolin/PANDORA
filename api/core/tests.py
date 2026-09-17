from django.db import connection
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .patterns import AIService, AISettings


class SingletonPatternTests(SimpleTestCase):
    def test_configuration_is_unique_per_process(self):
        first = AISettings.get_instance()
        second = AISettings.instance()
        self.assertIs(first, second)
        self.assertIs(AIService().get_configuration(), first)


class HealthTests(TestCase):
    def test_health_checks_database_connection(self):
        response = APIClient().get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["database"], connection.vendor)
