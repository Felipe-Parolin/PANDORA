from django.conf import settings
from django.db import models


class Vehicle(models.Model):
    class Type(models.TextChoices):
        PICKUP = "PICKUP", "Picape"
        VAN = "VAN", "Van"
        TRUCK = "TRUCK", "Caminhão"
        OTHER = "OTHER", "Outro"

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Disponível"
        MAINTENANCE = "MAINTENANCE", "Em manutenção"
        INACTIVE = "INACTIVE", "Inativo"

    plate = models.CharField(max_length=7, unique=True)
    brand = models.CharField(max_length=80)
    model = models.CharField(max_length=100)
    vehicle_type = models.CharField(max_length=16, choices=Type.choices, default=Type.PICKUP)
    capacity_kg = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("plate",)

    def __str__(self):
        return f"{self.plate} · {self.model}"


class TransportTask(models.Model):
    class Leg(models.TextChoices):
        DELIVERY = "DELIVERY", "Entrega"
        RETURN = "RETURN", "Coleta de devolução"

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "A planejar"
        IN_TRANSIT = "IN_TRANSIT", "Em transporte"
        COMPLETED = "COMPLETED", "Concluído"
        CANCELLED = "CANCELLED", "Cancelado"

    quote = models.ForeignKey("rentals.RentalQuote", on_delete=models.PROTECT, related_name="transport_tasks")
    leg = models.CharField(max_length=10, choices=Leg.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, null=True, blank=True, related_name="transport_tasks")
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="driving_tasks")
    address = models.CharField(max_length=255)
    complement = models.CharField(max_length=120, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    departed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_transport_tasks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("scheduled_at", "created_at")
        constraints = [models.UniqueConstraint(fields=("quote", "leg"), name="unique_quote_transport_leg")]

    def __str__(self):
        return f"{self.quote.number} · {self.get_leg_display()}"
