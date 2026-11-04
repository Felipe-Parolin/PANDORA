from django.conf import settings
from django.db import models
from django.db.models import Q


class PurchaseRecommendation(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente de análise"
        APPROVED = "APPROVED", "Aprovada"
        REJECTED = "REJECTED", "Rejeitada"
        ACQUIRED = "ACQUIRED", "Já adquirida"

    category = models.ForeignKey("assets.EquipmentCategory", on_delete=models.PROTECT, related_name="purchase_recommendations")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    priority = models.CharField(max_length=10, default="MEDIUM")
    current_total = models.PositiveIntegerField(default=0)
    current_available = models.PositiveIntegerField(default=0)
    demand_events = models.PositiveIntegerField(default=0)
    maintenance_orders = models.PositiveIntegerField(default=0)
    unavailable_days = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    suggested_quantity = models.PositiveSmallIntegerField(default=1)
    evidence = models.JSONField(default=dict, blank=True)
    rationale = models.TextField()
    decision_note = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_decisions")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("category",), condition=Q(status="PENDING"), name="unique_pending_purchase_rec_category")]


class MarketingCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        READY = "READY", "Pronta para envio"
        SENT = "SENT", "Enviada"
        FAILED = "FAILED", "Falha"
        PARTIAL = "PARTIAL", "Parcialmente enviada"

    title = models.CharField(max_length=160)
    subject = models.CharField(max_length=180)
    body_html = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)
    result_log = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="marketing_campaigns")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class Receivable(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Em aberto"
        PAID = "PAID", "Baixada"

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="receivables")
    quote = models.ForeignKey("rentals.RentalQuote", on_delete=models.PROTECT, related_name="receivables", null=True, blank=True)
    description = models.CharField(max_length=240)
    issue_date = models.DateField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    monthly_interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    grace_days = models.PositiveSmallIntegerField(default=5)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_receivables")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("due_date", "pk")
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="receivable_positive_amount"),
            models.CheckConstraint(condition=Q(monthly_interest_rate__gte=0), name="receivable_nonnegative_interest"),
        ]

    @property
    def number(self):
        return f"CR-{self.pk:06d}"


class Payment(models.Model):
    class Method(models.TextChoices):
        PIX = "PIX", "Pix"
        CASH = "CASH", "Dinheiro"
        TRANSFER = "TRANSFER", "Transferência"
        CARD = "CARD", "Cartão"
        OTHER = "OTHER", "Outro"

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField()
    method = models.CharField(max_length=10, choices=Method.choices)
    notes = models.TextField(blank=True)
    principal = models.DecimalField(max_digits=16, decimal_places=2)
    interest = models.DecimalField(max_digits=16, decimal_places=2)
    total = models.DecimalField(max_digits=16, decimal_places=2)
    idempotency_key = models.UUIDField(unique=True, editable=False)
    request_hash = models.CharField(max_length=64, editable=False)
    snapshot = models.JSONField(default=dict, editable=False)
    snapshot_hash = models.CharField(max_length=64, editable=False)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_payments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def number(self):
        return f"REC-{self.pk:06d}"


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    receivable = models.OneToOneField(Receivable, on_delete=models.PROTECT, related_name="allocation")
    principal = models.DecimalField(max_digits=12, decimal_places=2)
    interest = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ("pk",)
