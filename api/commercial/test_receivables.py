from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from accounts.models import AccessGroup, User
from assets.models import Equipment, EquipmentCategory
from core.models import AuditLog
from customers.models import Customer
from rentals.models import RentalQuote, RentalInspection
from .models import Receivable, Payment, PaymentAllocation
from .receivables import charges, post_quote_receivable


class FinanceFixtures:
    def make_fixtures(self):
        self.today = timezone.localdate()
        group = AccessGroup.objects.create(name="Financeiro de teste", permissions=["*"])
        self.user = User.objects.create_user("finance@example.invalid", "test", full_name="Operador de teste", access_group=group)
        self.customer = Customer.objects.create(person_type="PF", name="Cliente de teste", document="12345678909", phone="19999999999")
        self.other = Customer.objects.create(person_type="PJ", name="Outro cliente", document="11222333000181", phone="1933333333")
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def title(self, amount="1000.00", days_late=0, **extra):
        return Receivable.objects.create(customer=self.customer, description="Locação de teste", issue_date=self.today-timedelta(days=40), due_date=self.today-timedelta(days=days_late), amount=Decimal(amount), created_by=self.user, **extra)

    def preview(self, ids, customer=None, date=None, expected=200):
        response = self.client.post("/api/receivables/settlement-preview/", {"customer": customer or self.customer.pk, "receivable_ids": ids, "payment_date": str(date or self.today)}, format="json")
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def payload(self, preview, **extra):
        return {"customer": preview["customer"], "receivable_ids": [item["id"] for item in preview["items"]], "payment_date": preview["payment_date"], "method": "PIX", "notes": "Pagamento de teste", "idempotency_key": str(uuid4()), "calculation_token": preview["calculation_token"], "expected_total": preview["total"], **extra}

    def pay(self, payload, expected=201):
        response = self.client.post("/api/receivables/settle/", payload, format="json")
        self.assertEqual(response.status_code, expected, response.data)
        return response.data


class ReceivablesTests(FinanceFixtures, TestCase):
    def setUp(self):
        self.make_fixtures()

    def test_grace_boundary_and_daily_simple_interest_rounding(self):
        title = self.title()
        for day, expected in [(0,"0.00"),(5,"0.00"),(6,"0.33"),(35,"10.00"),(65,"20.00")]:
            value = charges(title, title.due_date+timedelta(days=day))
            self.assertEqual(value["interest"], expected)
            self.assertEqual(value["charged_days"], max(day-5,0))
        title.monthly_interest_rate = Decimal("0")
        self.assertEqual(charges(title, self.today+timedelta(days=400))["interest"], "0.00")

    def test_multi_title_settlement_preserves_unselected_and_receipt_snapshot(self):
        first, second, untouched = self.title(days_late=6), self.title("300.00",35), self.title("50.00")
        preview = self.preview([second.pk,first.pk])
        self.assertEqual(preview["interest"], "3.33")
        self.assertEqual(preview["total"], "1303.33")
        paid = self.pay(self.payload(preview))
        self.assertEqual(PaymentAllocation.objects.count(),2)
        self.assertEqual(Receivable.objects.filter(status="OPEN").get().pk,untouched.pk)
        snapshot = paid["snapshot"]
        self.customer.name = "Nome alterado depois"; self.customer.save(update_fields=["name"])
        first.due_date = self.today; first.save(update_fields=["due_date"])
        pdf = self.client.get(f"/api/payments/{paid['id']}/receipt/")
        self.assertEqual(pdf.status_code,200)
        self.assertEqual(pdf["Content-Type"],"application/pdf")
        self.assertIn("no-store",pdf["Cache-Control"])
        text = "".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn("Cliente de teste",text);self.assertNotIn("Nome alterado depois",text)
        self.assertIn("1.303,33",text);self.assertIn("Documento não fiscal",text)
        self.assertEqual(self.client.get(f"/api/payments/{paid['id']}/").data["snapshot"],snapshot)
        self.assertEqual(AuditLog.objects.filter(entity="Payment",action="settled").count(),1)

    def test_idempotent_retry_and_duplicate_or_reused_key_rejected(self):
        title = self.title(); payload = self.payload(self.preview([title.pk]))
        first = self.pay(payload)
        retry = self.pay(payload,200)
        self.assertEqual(first["id"],retry["id"])
        self.pay({**payload,"idempotency_key":str(uuid4())},400)
        self.pay({**payload,"notes":"Outro pagamento"},400)
        self.assertEqual(Payment.objects.count(),1)

    def test_stale_preview_rejected_after_due_or_interest_edit(self):
        title = self.title(days_late=10); payload = self.payload(self.preview([title.pk]))
        response=self.client.patch(f"/api/receivables/{title.pk}/",{"due_date":str(self.today),"monthly_interest_rate":"0.50"},format="json")
        self.assertEqual(response.status_code,200,response.data)
        self.pay(payload,400)
        self.assertFalse(Payment.objects.exists())
        updated = self.preview([title.pk]); self.assertEqual(updated["interest"],"0.00")
        self.pay(self.payload(updated))
        self.assertTrue(AuditLog.objects.filter(entity="Receivable",action="updated").exists())

    def test_selection_validation_dates_and_client_total_are_not_trusted(self):
        title=self.title(); other=Receivable.objects.create(customer=self.other,description="Outra conta",issue_date=self.today,due_date=self.today,amount=10,created_by=self.user)
        for ids in [[],[title.pk,title.pk],[title.pk,other.pk],[999999]]:
            self.preview(ids,expected=400)
        self.preview([title.pk],date=self.today+timedelta(days=1),expected=400)
        self.preview([title.pk],date=title.issue_date-timedelta(days=1),expected=400)
        payload=self.payload(self.preview([title.pk]))
        self.pay({**payload,"expected_total":"1.00"},400)
        self.pay({**payload,"calculation_token":"0"*64},400)
        self.assertFalse(Payment.objects.exists())

    def test_paid_titles_cannot_be_edited_deleted_or_changed_by_put(self):
        title=self.title();self.pay(self.payload(self.preview([title.pk])))
        self.assertEqual(self.client.patch(f"/api/receivables/{title.pk}/",{"due_date":str(self.today)},format="json").status_code,400)
        self.assertEqual(self.client.delete(f"/api/receivables/{title.pk}/").status_code,405)
        self.assertEqual(self.client.put(f"/api/receivables/{title.pk}/",{},format="json").status_code,405)
        self.assertEqual(self.client.delete("/api/payments/1/").status_code,405)

    def test_interest_exceeding_storage_limits_returns_validation_without_partial_writes(self):
        title=self.title('9999999999.99',days_late=100000,monthly_interest_rate=Decimal('100'))
        self.preview([title.pk],expected=400)
        self.assertFalse(Payment.objects.exists());self.assertFalse(PaymentAllocation.objects.exists())

    def test_customer_search_accepts_the_document_mask_displayed_in_the_table(self):
        self.title()
        response=self.client.get('/api/receivables/customers/',{'search':'123.456.789-09'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['count'],1)
        self.assertEqual(response.data['results'][0]['id'],self.customer.pk)
        response=self.client.get('/api/receivables/customers/',{'search':'12345678909'})
        self.assertEqual(response.data['count'],1)

    def test_manual_title_validates_dates_amount_and_immutable_fields(self):
        payload={"customer":self.customer.pk,"description":"Serviço faturado","issue_date":str(self.today),"due_date":str(self.today+timedelta(days=2)),"amount":"125.50"}
        response=self.client.post('/api/receivables/',payload,format='json');self.assertEqual(response.status_code,201,response.data)
        title=Receivable.objects.get(pk=response.data['id']);self.assertEqual(title.monthly_interest_rate,1);self.assertEqual(title.grace_days,5)
        for change in ({"amount":"0"},{"monthly_interest_rate":"-1"},{"grace_days":-1},{"issue_date":str(self.today+timedelta(days=1))},{"due_date":str(self.today-timedelta(days=1))}):
            self.assertEqual(self.client.post('/api/receivables/',{**payload,**change},format='json').status_code,400)
        self.assertEqual(self.client.patch(f'/api/receivables/{title.pk}/',{'amount':'1.00'},format='json').status_code,400)
        self.assertEqual(self.client.patch(f'/api/receivables/{title.pk}/',{'customer':self.other.pk},format='json').status_code,400)

    def test_customer_summary_totals_filters_and_ten_item_pagination(self):
        paid=self.title('500.00',35);self.pay(self.payload(self.preview([paid.pk])))
        late=self.title('1000.00',6);self.title('100.00',3);self.title('50.00',0)
        summary=self.client.get('/api/receivables/customers/',{'situation':'overdue'}).data['results'][0]
        self.assertEqual(Decimal(summary['billed']),Decimal('1650'))
        self.assertEqual(Decimal(summary['open_total']),Decimal('1150.33'))
        self.assertEqual(Decimal(summary['paid_total']),Decimal('505.00'))
        self.assertEqual(summary['open_count'],3);self.assertEqual(summary['paid_count'],1)
        for i in range(11):self.title('1.00')
        listing=self.client.get('/api/receivables/',{'customer':self.customer.pk,'status':'OPEN'})
        self.assertEqual(len(listing.data['results']),10);self.assertIsNotNone(listing.data['next'])
        lookup=self.client.get('/api/receivables/',{'search':late.number})
        self.assertEqual(lookup.data['count'],1)
        self.assertEqual(self.client.get('/api/receivables/customers/',{'search':'inexistente'}).data['count'],0)
        self.assertEqual(self.client.get('/api/receivables/',{'customer':'invalid'}).status_code,400)

    def test_receipt_detects_tampering_and_long_receipt_has_repeated_headers(self):
        titles=[self.title('1.00') for _ in range(36)]
        data=self.pay(self.payload(self.preview([item.pk for item in titles])))
        response=self.client.get(f"/api/payments/{data['id']}/receipt/")
        pages=PdfReader(BytesIO(response.content)).pages
        self.assertGreater(len(pages),1)
        self.assertIn('Conta / descrição',pages[1].extract_text())
        Payment.objects.filter(pk=data['id']).update(snapshot={"changed":True})
        self.assertEqual(self.client.get(f"/api/payments/{data['id']}/receipt/").status_code,400)

    def test_acl_separates_consultation_from_payment_and_operational_roles(self):
        title=self.title();paid=self.pay(self.payload(self.preview([title.pk])))
        viewer=AccessGroup.objects.create(name='Consulta financeira',permissions=['commercial.receivables.view'])
        self.user.access_group=viewer;self.user.save(update_fields=['access_group'])
        for url in ['/api/receivables/','/api/receivables/customers/',f"/api/payments/{paid['id']}/receipt/"]:
            self.assertEqual(self.client.get(url).status_code,200,url)
        self.assertEqual(self.client.post('/api/receivables/settle/',{},format='json').status_code,403)
        self.assertEqual(self.client.patch(f'/api/receivables/{title.pk}/',{},format='json').status_code,403)
        self.user.access_group=None;self.user.role='MAINTENANCE';self.user.save(update_fields=['access_group','role'])
        self.assertEqual(self.client.get('/api/receivables/').status_code,403)
        self.assertEqual(self.client.get(f"/api/payments/{paid['id']}/receipt/").status_code,403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/receivables/').status_code,401)

    def test_posting_only_after_delivery_and_only_positive_unbilled_difference(self):
        quote=RentalQuote.objects.create(customer=self.customer,start_date=self.today,end_date=self.today+timedelta(days=4),total=Decimal('100'),created_by=self.user)
        self.assertIsNone(post_quote_receivable(quote,self.user))
        quote.delivered_at=timezone.now();quote.save(update_fields=['delivered_at'])
        with patch('commercial.receivables.Receivable.objects.create',side_effect=RuntimeError('Falha de teste')):
            with self.assertRaises(RuntimeError):post_quote_receivable(quote,self.user)
        self.assertEqual(quote.receivables.count(),0)
        first=post_quote_receivable(quote,self.user)
        self.assertEqual(first.amount,100);self.assertEqual(first.due_date,quote.end_date)
        self.assertIsNone(post_quote_receivable(quote,self.user))
        self.pay(self.payload(self.preview([first.pk])))
        quote.total=Decimal('140');quote.end_date+=timedelta(days=2);quote.save(update_fields=['total','end_date'])
        second=post_quote_receivable(quote,self.user)
        self.assertEqual(second.amount,40);self.assertEqual(second.due_date,quote.end_date)
        first.refresh_from_db();self.assertEqual(first.amount,100);self.assertEqual(first.status,'PAID')


class DeliveryBillingTests(FinanceFixtures, TestCase):
    def setUp(self):
        self.make_fixtures()
        category=EquipmentCategory.objects.create(name='Categoria financeira')
        self.assets=[Equipment.objects.create(category=category,name=f'Item {i}',internal_code=f'FIN-{i}',serial_number=f'FIN-{i}',daily_rate=100) for i in range(2)]

    def make_quote(self):
        response=self.client.post('/api/rental-quotes/',{'customer':self.customer.pk,'start_date':str(self.today),'end_date':str(self.today+timedelta(days=2)),'conditions':'Pagamento na devolução','status':'APPROVED','items':[{'equipment_id':item.pk,'daily_rate':'100','start_date':str(self.today),'end_date':str(self.today+timedelta(days=2))} for item in self.assets]},format='json')
        self.assertEqual(response.status_code,201,response.data)
        return RentalQuote.objects.get(pk=response.data['id'])

    def inspect(self, quote, item):
        inspection=RentalInspection.objects.get(quote=quote,equipment=item,inspection_type='PRE_RENTAL')
        result=self.client.patch(f'/api/rental-inspections/{inspection.pk}/',{'checklist':[{**entry,'status':'OK'} for entry in inspection.checklist],'result':'APPROVED','condition':'GOOD'},format='json')
        self.assertEqual(result.status_code,200,result.data)

    def test_actual_partial_delivery_posts_once_and_extension_posts_difference(self):
        quote=self.make_quote()
        self.assertFalse(quote.receivables.exists())
        rejected=self.client.post(f'/api/rental-quotes/{quote.pk}/deliver/',{'equipment_ids':[self.assets[0].pk]},format='json')
        self.assertEqual(rejected.status_code,400);self.assertFalse(quote.receivables.exists())
        for item in self.assets:
            self.inspect(quote,item)
        for item in self.assets:
            result=self.client.post(f'/api/rental-quotes/{quote.pk}/deliver/',{'equipment_ids':[item.pk]},format='json')
            self.assertEqual(result.status_code,200,result.data)
            self.assertEqual(quote.receivables.count(),1)
        first=quote.receivables.get();self.assertEqual(first.amount,600)
        response=self.client.post(f'/api/rental-quotes/{quote.pk}/extend/',{'equipment_ids':[self.assets[0].pk],'new_end_date':str(self.today+timedelta(days=4))},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(quote.receivables.count(),2)
        self.assertEqual(quote.receivables.exclude(pk=first.pk).get().amount,200)

    def test_financial_posting_failure_rolls_back_actual_delivery(self):
        # A falha financeira precisa interromper a mesma transação da movimentação.
        quote=self.make_quote();self.inspect(quote,self.assets[0])
        with patch('commercial.receivables.post_quote_receivable',side_effect=RuntimeError('Falha financeira de teste')):
            with self.assertRaises(RuntimeError):
                self.client.post(f'/api/rental-quotes/{quote.pk}/deliver/',{'equipment_ids':[self.assets[0].pk]},format='json')
        quote.refresh_from_db();self.assertEqual(quote.status,'APPROVED')
        self.assertEqual(quote.items.get(equipment=self.assets[0]).stage,'PENDING')
        self.assertFalse(quote.receivables.exists())


class ConcurrentSettlementTests(FinanceFixtures, TransactionTestCase):
    def setUp(self):
        self.make_fixtures()

    def run_race(self,same_key):
        if connection.vendor!='postgresql':self.skipTest('Bloqueio concorrente exige PostgreSQL')
        title=self.title();payload=self.payload(self.preview([title.pk]));barrier=Barrier(2)
        def request(index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'");cursor.execute("SET statement_timeout = '15s'")
                client=APIClient();client.force_authenticate(User.objects.get(pk=self.user.pk))
                data={**payload}
                if not same_key and index:data['idempotency_key']=str(uuid4())
                barrier.wait(timeout=10)
                return client.post('/api/receivables/settle/',data,format='json').status_code
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(request,range(2)))
        self.assertEqual(sorted(results),[200,201] if same_key else [201,400])
        self.assertEqual(Payment.objects.count(),1);self.assertEqual(PaymentAllocation.objects.count(),1)

    def test_same_payment_retried_concurrently_is_idempotent(self):self.run_race(True)
    def test_different_payments_cannot_settle_the_same_title(self):self.run_race(False)
