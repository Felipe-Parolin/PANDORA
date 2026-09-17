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
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rental_quotes")
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
        self.total = max(subtotal - self.discount, Decimal("0"))
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
