from django.test import TestCase

from .serializers import CustomerSerializer


class CustomerDocumentTests(TestCase):
    def test_accepts_valid_cpf_and_normalizes_formatting(self):
        serializer = CustomerSerializer(data={
            "person_type": "PF", "name": "Cliente", "document": "123.456.789-09", "phone": "19999999999",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["document"], "12345678909")

    def test_rejects_invalid_cnpj_check_digits(self):
        serializer = CustomerSerializer(data={
            "person_type": "PJ", "name": "Empresa", "document": "11.111.111/1111-11", "phone": "19999999999",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("document", serializer.errors)

    def test_accepts_alphanumeric_cnpj_without_discarding_letters(self):
        serializer = CustomerSerializer(data={
            "person_type": "PJ", "name": "Empresa fictícia", "document": "12.abc.345/01de-35", "phone": "19999999999",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["document"], "12ABC34501DE35")

    def test_rejects_formatted_duplicate_as_validation_error(self):
        from .models import Customer

        Customer.objects.create(person_type="PF", name="Existente", document="12345678909", phone="19999999999")
        serializer = CustomerSerializer(data={
            "person_type": "PF", "name": "Outro", "document": "123.456.789-09", "phone": "19999999999",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("document", serializer.errors)
