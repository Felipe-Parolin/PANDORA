"""Faturamento contratual e baixa integral dos títulos selecionados, sem emissão fiscal."""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.models import AuditLog
from customers.models import Customer
from .models import Payment, PaymentAllocation, Receivable

CENT = Decimal("0.01")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def charges(title, on_date):
    late_days = max(0, (on_date - title.due_date).days)
    charged_days = max(0, late_days - title.grace_days)
    interest = (title.amount * title.monthly_interest_rate / Decimal("100") / Decimal("30") * charged_days).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "id": title.pk, "number": title.number, "description": title.description,
        "quote_number": title.quote.number if title.quote_id else "",
        "issue_date": str(title.issue_date), "due_date": str(title.due_date),
        "principal": str(title.amount), "interest": str(interest), "total": str(title.amount + interest),
        "late_days": late_days, "charged_days": charged_days,
        "monthly_interest_rate": str(title.monthly_interest_rate), "grace_days": title.grace_days,
    }


@transaction.atomic
def post_quote_receivable(quote, actor):
    """O chamador bloqueia a locação; só a diferença ainda não faturada gera título."""
    if not quote.delivered_at:
        return None
    Customer.objects.select_for_update().get(pk=quote.customer_id)
    issued = quote.receivables.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    amount = (quote.total - issued).quantize(CENT, rounding=ROUND_HALF_UP)
    if amount <= 0:
        return None
    title = Receivable.objects.create(
        customer_id=quote.customer_id, quote=quote, amount=amount,
        description=f"{'Complemento da locação' if issued else 'Locação'} {quote.number}",
        issue_date=timezone.localdate(), due_date=quote.end_date, created_by=actor,
    )
    AuditLog.objects.create(user=actor, entity="Receivable", record_id=title.pk, action="issued", data={"quote": quote.pk, "amount": str(amount), "due_date": str(title.due_date)})
    return title


def selected_titles(customer_id, ids, lock=False):
    qs = Receivable.objects.filter(customer_id=customer_id, pk__in=ids)
    if lock:
        qs = qs.select_for_update(of=("self",))
    titles = list(qs.select_related("quote").order_by("pk"))
    if len(titles) != len(ids) or any(item.status != Receivable.Status.OPEN for item in titles):
        raise ValidationError({"receivable_ids": "Selecione apenas contas em aberto deste cliente. Atualize a lista se uma delas já foi baixada."})
    return titles


def payment_preview(customer_id, ids, on_date, lock=False):
    titles = selected_titles(customer_id, ids, lock)
    if any(on_date < item.issue_date for item in titles):
        raise ValidationError({"payment_date": "O pagamento não pode ser anterior à emissão de uma das contas."})
    items = [charges(item, on_date) for item in titles]
    principal = sum((item.amount for item in titles), Decimal("0"))
    interest = sum((Decimal(item["interest"]) for item in items), Decimal("0"))
    if any(Decimal(item["interest"]) > Decimal("9999999999.99") for item in items) or principal + interest > Decimal("99999999999999.99"):
        raise ValidationError({"receivable_ids": "O valor calculado excede o limite de registro. Revise o vencimento e a taxa das contas antes de baixar."})
    result = {"customer": customer_id, "payment_date": str(on_date), "items": items, "principal": str(principal), "interest": str(interest), "total": str(principal + interest)}
    result["calculation_token"] = digest(result)
    return result, titles


@transaction.atomic
def settle(validated, actor):
    data = dict(validated)
    customer = Customer.objects.select_for_update().get(pk=data["customer"])
    request_hash = digest({key: str(value) if key != "receivable_ids" else sorted(value) for key, value in data.items()})
    previous = Payment.objects.filter(idempotency_key=data["idempotency_key"]).first()
    if previous:
        if previous.customer_id != customer.pk or previous.request_hash != request_hash:
            raise ValidationError({"idempotency_key": "Esta identificação já foi usada para outro pagamento."})
        return previous, False
    preview, titles = payment_preview(customer.pk, data["receivable_ids"], data["payment_date"], lock=True)
    if preview["calculation_token"] != data["calculation_token"] or Decimal(preview["total"]) != data["expected_total"]:
        raise ValidationError({"calculation_token": "As condições das contas mudaram. Confira uma nova prévia antes de baixar."})
    try:
        with transaction.atomic():
            payment = Payment.objects.create(
                customer=customer, payment_date=data["payment_date"], method=data["method"], notes=data.get("notes", ""),
                principal=preview["principal"], interest=preview["interest"], total=preview["total"],
                idempotency_key=data["idempotency_key"], request_hash=request_hash, received_by=actor,
            )
    except IntegrityError:
        raise ValidationError({"idempotency_key": "Esta identificação já foi usada para outro pagamento."})
    for title, entry in zip(titles, preview["items"]):
        PaymentAllocation.objects.create(payment=payment, receivable=title, principal=title.amount, interest=entry["interest"])
    Receivable.objects.filter(pk__in=[item.pk for item in titles]).update(status=Receivable.Status.PAID, updated_at=timezone.now())
    snapshot = {
        "schema_version": 1, "number": payment.number, "payment_date": str(payment.payment_date),
        "method": payment.get_method_display(), "notes": payment.notes,
        "customer": {"name": customer.name, "document": customer.document, "address": customer.address, "number": customer.address_number, "cep": customer.address_cep},
        "received_by": actor.full_name, "recorded_at": payment.created_at.isoformat(),
        **{key: preview[key] for key in ("items", "principal", "interest", "total")},
    }
    payment.snapshot, payment.snapshot_hash = snapshot, digest(snapshot)
    payment.save(update_fields=("snapshot", "snapshot_hash"))
    AuditLog.objects.create(user=actor, entity="Payment", record_id=payment.pk, action="settled", data={"number": payment.number, "receivables": [item.pk for item in titles], "total": preview["total"], "snapshot_hash": payment.snapshot_hash})
    return payment, True
