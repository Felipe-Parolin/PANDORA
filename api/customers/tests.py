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

    def test_valid_numeric_cnpj_and_whitespace_normalization(self):
        serializer = CustomerSerializer(data={
            "person_type": "PJ", "name": "Empresa", "document": " 04 . 252 . 011 / 0001 - 10 ", "phone": "19999999999",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["document"], "04252011000110")

    def test_rejects_wrong_person_type_invalid_digits_and_unsupported_characters(self):
        for person_type, document in (
            ("PF", "04252011000110"), ("PJ", "12345678909"),
            ("PJ", "12ABC34501DE36"), ("PJ", "04252011000111"),
            ("PF", "11111111111"), ("PF", "12345678900"),
            ("PF", "123ABC78909"), ("PJ", "12@BC34501DE35"),
        ):
            with self.subTest(person_type=person_type, document=document):
                serializer = CustomerSerializer(data={"person_type": person_type, "name": "Teste", "document": document, "phone": "19999999999"})
                self.assertFalse(serializer.is_valid())
                self.assertIn("document", serializer.errors)

    def test_edit_self_keeps_marketing_consent_and_unsubscribe_token(self):
        from .models import Customer
        import uuid

        customer = Customer.objects.create(person_type="PJ", name="Empresa", document="12ABC34501DE35", phone="19999999999", marketing_opt_in=True)
        token = customer.marketing_unsubscribe_token
        serializer = CustomerSerializer(customer, data={"document": "12.abc.345/01de-35", "marketing_unsubscribe_token": str(uuid.uuid4())}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        customer.refresh_from_db()
        self.assertTrue(customer.marketing_opt_in)
        self.assertEqual(customer.marketing_unsubscribe_token, token)
        self.assertEqual(customer.document, "12ABC34501DE35")

    def test_alphanumeric_and_unformatted_duplicates_have_clear_message(self):
        from .models import Customer

        Customer.objects.create(person_type="PJ", name="Existente", document="12ABC34501DE35", phone="19999999999")
        for document in ("12.abc.345/01de-35", "12ABC34501DE35"):
            serializer = CustomerSerializer(data={"person_type": "PJ", "name": "Outro", "document": document, "phone": "19999999999"})
            self.assertFalse(serializer.is_valid())
            self.assertEqual(str(serializer.errors["document"][0]), "Já existe um cliente com este CPF/CNPJ.")

    def test_partial_edit_cannot_change_person_type_incompatibly(self):
        from .models import Customer

        customer = Customer.objects.create(person_type="PF", name="Cliente", document="12345678909", phone="19999999999")
        serializer = CustomerSerializer(customer, data={"person_type": "PJ"}, partial=True)
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
