from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import AccessGroup, User
from .models import Customer
from .serializers import CustomerSerializer


class CustomerAddressTests(TestCase):
    def test_notes_and_postal_code_are_saved_without_requiring_address_on_legacy_customers(self):
        customer = Customer.objects.create(person_type="PF", name="Cliente", document="12345678909", phone="19999999999")
        serializer = CustomerSerializer(customer, data={"notes": "Portão lateral", "address": "Rua de teste, 120", "address_cep": "13614-032"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        customer.refresh_from_db()
        self.assertEqual(customer.notes, "Portão lateral")
        self.assertEqual(customer.address_cep, "13614032")
        for value in ("123", "abcdefgh", "136140320"):
            serializer = CustomerSerializer(customer, data={"address_cep": value}, partial=True)
            self.assertFalse(serializer.is_valid())

    @patch("rentals.freight.lookup_cep", return_value={"cep": "13614032", "street": "Rua de teste", "city": "Leme", "state": "SP"})
    def test_lookup_requires_customer_management_without_rental_permission(self, lookup):
        group = AccessGroup.objects.create(name="Cadastro de clientes", permissions=["customers.view", "customers.manage"])
        user = User.objects.create_user("cadastro@example.invalid", full_name="Cadastro", access_group=group)
        client = APIClient(); client.force_authenticate(user)
        response = client.get("/api/customers/lookup-address/", {"cep": "13614032"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["street"], "Rua de teste")
        lookup.assert_called_once_with("13614032")
        lookup.reset_mock()
        group.permissions = ["customers.view"]; group.save()
        user.refresh_from_db(); client.force_authenticate(user)
        self.assertEqual(client.get("/api/customers/lookup-address/", {"cep": "13614032"}).status_code, 403)
        lookup.assert_not_called()
