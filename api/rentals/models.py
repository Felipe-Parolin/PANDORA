import uuid
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class RentalQuote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        SENT = "SENT", "Enviado"
        APPROVED = "APPROVED", "Aprovado / reservado"
        ACTIVE = "ACTIVE", "Em locação"
        RETURNED = "RETURNED", "Devolvido / aguardando inspeção"
        COMPLETED = "COMPLETED", "Concluído"
        CANCELLED = "CANCELLED", "Cancelado"
        EXPIRED = "EXPIRED", "Expirado"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    number = models.CharField(max_length=30, unique=True, blank=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="rental_quotes")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    conditions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    delivery_transport_required = models.BooleanField(default=False)
    return_transport_required = models.BooleanField(default=False)
    delivery_address = models.CharField(max_length=255, blank=True)
    return_address = models.CharField(max_length=255, blank=True)
    transport_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rental_quotes")
    reserved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reserved_rentals", null=True, blank=True)
    reserved_at = models.DateTimeField(null=True, blank=True)
    delivered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="delivered_rentals", null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_conditions = models.TextField(blank=True)
    returned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="returned_rentals", null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    return_conditions = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cancelled_rentals", null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError("A data final deve ser igual ou posterior à data inicial.")

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = f"ORC-{str(self.public_id)[:8].upper()}"
        super().save(*args, **kwargs)

    def recalculate(self):
        subtotal = sum((item.total for item in self.items.all()), Decimal("0"))
        self.subtotal = subtotal
        self.total = max(subtotal + self.transport_fee - self.discount, Decimal("0"))
        self.save(update_fields=("subtotal", "total", "updated_at"))


class RentalItem(models.Model):
    quote = models.ForeignKey(RentalQuote, on_delete=models.CASCADE, related_name="items")
    equipment = models.ForeignKey("assets.Equipment", on_delete=models.PROTECT, related_name="rental_items")
    daily_rate = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_days = models.PositiveIntegerField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    condition_out = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("quote", "equipment"), name="unique_equipment_per_quote")]

    def save(self, *args, **kwargs):
        self.total = self.daily_rate * self.quantity_days
        super().save(*args, **kwargs)


class RentalInspection(models.Model):
    class Type(models.TextChoices):
        PRE_RENTAL = "PRE_RENTAL", "Pré-locação"
        RETURN = "RETURN", "Devolução"

    class Result(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        APPROVED = "APPROVED", "Aprovado"
        APPROVED_WITH_NOTES = "APPROVED_WITH_NOTES", "Aprovado com ressalvas"
        BLOCKED = "BLOCKED", "Impedido"

    class Condition(models.TextChoices):
        GOOD = "GOOD", "Bom"
        REGULAR = "REGULAR", "Regular"
        DAMAGED = "DAMAGED", "Avariado"
        CRITICAL = "CRITICAL", "Crítico"

    quote = models.ForeignKey(RentalQuote, on_delete=models.CASCADE, related_name="inspections")
    equipment = models.ForeignKey("assets.Equipment", on_delete=models.PROTECT, related_name="rental_inspections")
    inspection_type = models.CharField(max_length=20, choices=Type.choices)
    result = models.CharField(max_length=30, choices=Result.choices, default=Result.PENDING)
    condition = models.CharField(max_length=20, choices=Condition.choices, default=Condition.GOOD)
    checklist = models.JSONField(default=list, blank=True)
    observations = models.TextField(blank=True)
    critical_impediment = models.BooleanField(default=False)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rental_inspections", null=True, blank=True)
    performed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("inspection_type", "equipment__internal_code")
        constraints = [
            models.UniqueConstraint(fields=("quote", "equipment", "inspection_type"), name="unique_rental_inspection"),
        ]


class RentalExtension(models.Model):
    quote = models.ForeignKey(RentalQuote, on_delete=models.CASCADE, related_name="extensions")
    previous_end_date = models.DateField()
    new_end_date = models.DateField()
    conditions = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rental_extensions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
