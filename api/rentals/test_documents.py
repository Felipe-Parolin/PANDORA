from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from accounts.models import AccessGroup, User
from assets.models import Equipment, EquipmentCategory
from core.models import AuditLog
from customers.models import Customer
from logistics.models import TransportTask
from .documents import render_document_pdf, snapshot_hash
from .models import RentalDocument, RentalInspection, RentalItem, RentalQuote


class RentalDocumentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = AccessGroup.objects.create(name="Documentos", permissions=["rentals.view", "rentals.manage"])
        cls.user = User.objects.create_user("documents@example.invalid", "test", full_name="Operador", access_group=cls.group)
        cls.customer = Customer.objects.create(person_type="PF", name="Cliente original", document="12345678909", phone="19999999999", address="Rua Cliente, 10")
        category = EquipmentCategory.objects.create(name="Documentos")
        cls.equipment = Equipment.objects.create(category=category, name="Equipamento original", brand="Marca", model="Modelo", serial_number="DOC-1", internal_code="DOC-1", daily_rate=100)
        cls.quote = RentalQuote.objects.create(
            customer=cls.customer, start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=2),
            conditions="Pagamento combinado <sem assinatura>\nSegunda condição.", created_by=cls.user,
            transport_fee=70, estimated_transport_fee=60, transport_fee_adjustment_reason="Acesso ao local",
            delivery_transport_required=True, return_transport_required=True,
            delivery_address="Rua Entrega, 20", delivery_complement="Portão 2", delivery_cep="13610050",
            return_address="Rua Coleta, 30", return_complement="Galpão", return_cep="13610050",
            requested_delivery_at=timezone.now(), requested_delivery_notes="Cliente pede pela manhã", discount_percent=10,
        )
        RentalItem.objects.create(quote=cls.quote, equipment=cls.equipment, daily_rate=100, quantity_days=3, total=300)
        cls.quote.recalculate()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/rental-quotes/{self.quote.pk}/documents/"

    def generate(self, kind="QUOTE", expected=201):
        response = self.client.post(self.url, {"kind": kind}, format="json")
        self.assertEqual(response.status_code, expected, response.data)
        return RentalDocument.objects.get(pk=response.data["id"])

    def pdf(self, document, expected=200):
        response = self.client.get(f"{self.url}{document.pk}/pdf/")
        self.assertEqual(response.status_code, expected)
        return response

    @staticmethod
    def text(response):
        return "\n".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)

    def test_unchanged_content_reuses_version_and_audit(self):
        first = self.generate()
        repeated = self.generate(expected=200)
        self.assertEqual(first.pk, repeated.pk)
        self.assertEqual(RentalDocument.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action="DOCUMENT_CREATED").count(), 1)
        self.assertEqual(first.content_hash, snapshot_hash(first.snapshot))

    def test_pdf_uses_snapshot_after_customer_equipment_and_quote_changes(self):
        first = self.generate()
        before = self.pdf(first).content
        Customer.objects.filter(pk=self.customer.pk).update(name="Cliente alterado", address="Outro endereço")
        Equipment.objects.filter(pk=self.equipment.pk).update(name="Equipamento alterado", serial_number="ALTERADO")
        RentalQuote.objects.filter(pk=self.quote.pk).update(conditions="Condições novas", transport_fee=99)
        after = self.pdf(first)
        self.assertEqual(before, after.content)
        self.assertIn("Cliente original", self.text(after))
        self.assertNotIn("Cliente alterado", self.text(after))
        second = self.generate()
        self.assertEqual(second.version, 2)
        self.assertEqual(second.snapshot["customer"]["name"], "Cliente alterado")
        first.refresh_from_db()
        self.assertEqual(first.snapshot["customer"]["name"], "Cliente original")
        self.assertNotEqual(first.content_hash, second.content_hash)

    def test_current_freight_requested_delivery_and_commercial_fields(self):
        document = self.generate()
        snapshot = document.snapshot
        self.assertNotIn("transport_estimate", snapshot)
        self.assertEqual(Decimal(snapshot["transport_fee"]), 70)
        self.assertEqual(Decimal(snapshot["estimated_transport_fee"]), 60)
        self.assertEqual(Decimal(snapshot["discount"]), 37)
        self.assertEqual(Decimal(snapshot["total"]), 333)
        self.assertEqual(snapshot["delivery_cep"], "13610050")
        self.assertTrue(snapshot["requested_delivery_at"])
        response = self.pdf(document)
        text = self.text(response)
        for value in ("Entrega desejada", "Cliente pede pela manhã", "R$ 333,00", "Acesso ao local", "Rua Entrega", "Rua Coleta", "Condições comerciais", "Documento comercial/operacional não fiscal", document.content_hash):
            self.assertIn(value, text)
        self.assertEqual(text.count("Condições comerciais"), 1)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_receipts_require_recorded_operations(self):
        for kind in ("DELIVERY", "RETURN", "INVALID", None):
            response = self.client.post(self.url, {"kind": kind}, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertFalse(RentalDocument.objects.exists())

    def record_operations(self):
        self.quote.delivered_at = timezone.now() - timedelta(hours=2)
        self.quote.returned_at = timezone.now()
        self.quote.delivered_by = self.user
        self.quote.returned_by = self.user
        self.quote.delivery_conditions = "Entregue no portão"
        self.quote.return_conditions = "Recebido no galpão"
        self.quote.save()
        self.quote.items.update(stage="COMPLETED", delivered_at=self.quote.delivered_at, returned_at=self.quote.returned_at,
                                delivered_by=self.user, returned_by=self.user, delivery_conditions=self.quote.delivery_conditions, return_conditions=self.quote.return_conditions)
        for kind in ("PRE_RENTAL", "RETURN"):
            RentalInspection.objects.create(
                quote=self.quote, equipment=self.equipment, inspection_type=kind, result="APPROVED",
                checklist=[{"label": "Cabo elétrico", "status": "OK", "notes": "Conferido"}],
                observations=f"Inspeção {kind}", performed_by=self.user, performed_at=timezone.now(),
            )

    def test_receipts_snapshot_actual_event_inspection_and_transport(self):
        self.record_operations()
        TransportTask.objects.create(quote=self.quote, leg="DELIVERY", status="COMPLETED", address="Endereço efetivo", completed_at=self.quote.delivered_at, created_by=self.user)
        quote_doc = self.generate()
        for kind, inspection_type, conditions in (("DELIVERY", "PRE_RENTAL", "Entregue no portão"), ("RETURN", "RETURN", "Recebido no galpão")):
            document = self.generate(kind)
            self.assertEqual(document.version, 1)
            self.assertEqual(document.snapshot["event_by"], "Operador")
            self.assertEqual(document.snapshot["event_conditions"], conditions)
            inspection = document.snapshot["equipment_condition"][0]
            self.assertEqual(inspection["performed_by"], "Operador")
            self.assertEqual(inspection["checklist"][0]["status"], "OK")
            text = self.text(self.pdf(document))
            for value in (conditions, f"Inspeção {inspection_type}", "Cabo elétrico: Conforme", "Conferido"):
                self.assertIn(value, text)
            if kind == "DELIVERY":
                self.assertIn("Endereço efetivo", text)
            RentalInspection.objects.filter(quote=self.quote, inspection_type=inspection_type).update(observations="Inspeção atualizada")
            updated = self.generate(kind)
            self.assertEqual(updated.version, 2)
            self.assertNotIn("Inspeção atualizada", self.text(self.pdf(document)))
        self.assertEqual(quote_doc.version, 1)

    def test_hash_tampering_blocks_download_and_reuse(self):
        document = self.generate()
        altered = deepcopy(document.snapshot)
        altered["total"] = "0.00"
        RentalDocument.objects.filter(pk=document.pk).update(snapshot=altered)
        self.pdf(document, expected=409)
        self.assertEqual(self.client.post(self.url, {"kind": "QUOTE"}).status_code, 409)

    def test_view_permission_can_read_and_download_but_cannot_generate(self):
        document = self.generate()
        self.group.permissions = ["rentals.view"]
        self.group.save()
        self.user.refresh_from_db()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.pdf(document)
        self.assertEqual(self.client.post(self.url, {"kind": "QUOTE"}).status_code, 403)

    def test_manage_permission_does_not_grant_read_permission(self):
        document = self.generate()
        self.group.permissions = ["rentals.manage"]
        self.group.save()
        self.user.refresh_from_db()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.pdf(document, expected=403)
        self.generate(expected=200)

    def test_anonymous_user_cannot_access_documents(self):
        document = self.generate()
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.post(self.url, {"kind": "QUOTE"}).status_code, 401)
        self.pdf(document, expected=401)

    def test_document_is_scoped_to_its_rental_and_history_contains_hash(self):
        document = self.generate()
        other = RentalQuote.objects.create(customer=self.customer, start_date=self.quote.start_date, end_date=self.quote.end_date, created_by=self.user)
        self.assertEqual(self.client.get(f"/api/rental-quotes/{other.pk}/documents/{document.pk}/pdf/").status_code, 404)
        history = self.client.get(self.url)
        self.assertEqual(history.data[0]["content_hash"], document.content_hash)
        self.assertEqual(history.data[0]["created_by_name"], "Operador")

    def test_documents_protect_rental_in_api_and_database(self):
        self.generate()
        self.assertEqual(self.client.delete(f"/api/rental-quotes/{self.quote.pk}/").status_code, 409)
        with self.assertRaises(ProtectedError):
            self.quote.delete()

    def test_version_is_unique_per_rental_and_kind(self):
        document = self.generate()
        with self.assertRaises(IntegrityError), transaction.atomic():
            RentalDocument.objects.create(quote=self.quote, kind=document.kind, version=1, snapshot={}, content_hash="", created_by=self.user)

    def test_hash_is_independent_of_json_key_order(self):
        self.assertEqual(snapshot_hash({"a": 1, "b": 2}), snapshot_hash({"b": 2, "a": 1}))

    def test_long_table_starts_on_first_page_and_keeps_totals_together(self):
        document = self.generate()
        original = document.snapshot["items"][0]
        document.snapshot["items"] = [dict(original, code=f"EQ-{index:03}", name="Equipamento com nome extenso para testar paginação e quebra de linha " * 2) for index in range(1, 46)]
        reader = PdfReader(BytesIO(render_document_pdf(document)))
        pages = [page.extract_text() for page in reader.pages]
        self.assertGreater(len(pages), 1)
        self.assertIn("EQ-001", pages[0])
        self.assertIn("EQ-045", "\n".join(pages))
        totals = next(page for page in pages if "R$ 333,00" in page)
        self.assertIn("R$ 300,00", totals)
        self.assertIn("R$ 70,00", totals)
        self.assertIn("R$ 37,00", totals)
