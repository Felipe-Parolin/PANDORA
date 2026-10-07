import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class MaintenancePlan(models.Model):
    class Type(models.TextChoices):
        PREVENTIVE = "PREVENTIVE", "Preventiva"
        SCHEDULED = "SCHEDULED", "Agendada"
        PRE_RENTAL = "PRE_RENTAL", "Antes da locação"
        POST_RENTAL = "POST_RENTAL", "Pós-locação"

    class Criticality(models.TextChoices):
        LOW = "LOW", "Baixa"
        MEDIUM = "MEDIUM", "Média"
        HIGH = "HIGH", "Alta"
        CRITICAL = "CRITICAL", "Crítica"

    equipment = models.ForeignKey("assets.Equipment", on_delete=models.CASCADE, related_name="maintenance_plans")
    name = models.CharField(max_length=150)
    maintenance_type = models.CharField(max_length=20, choices=Type.choices)
    interval_days = models.PositiveIntegerField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    last_service_date = models.DateField(null=True, blank=True)
    last_service_usage_hours = models.PositiveIntegerField(null=True, blank=True)
    advance_notice_days = models.PositiveIntegerField(default=15)
    advance_notice_usage_hours = models.PositiveIntegerField(default=10)
    criticality = models.CharField(max_length=20, choices=Criticality.choices, default=Criticality.MEDIUM)
    checklist = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("next_due_date", "equipment__name")


class ServiceOrder(models.Model):
    class Type(models.TextChoices):
        PREVENTIVE = "PREVENTIVE", "Preventiva"
        CORRECTIVE = "CORRECTIVE", "Corretiva"
        SCHEDULED = "SCHEDULED", "Agendada"
        PRE_RENTAL = "PRE_RENTAL", "Antes da locação"
        POST_RENTAL = "POST_RENTAL", "Pós-locação"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Aberta"
        SCHEDULED = "SCHEDULED", "Agendada"
        IN_PROGRESS = "IN_PROGRESS", "Em execução"
        WAITING_PARTS = "WAITING_PARTS", "Aguardando peças"
        ABANDONED = "ABANDONED", "Abandonada"
        COMPLETED = "COMPLETED", "Concluída"
        CANCELLED = "CANCELLED", "Cancelada"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    number = models.CharField(max_length=30, unique=True, blank=True)
    equipment = models.ForeignKey("assets.Equipment", on_delete=models.PROTECT, related_name="service_orders")
    plan = models.ForeignKey(MaintenancePlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="service_orders")
    rental_inspection = models.OneToOneField("rentals.RentalInspection", on_delete=models.SET_NULL, null=True, blank=True, related_name="service_order")
    maintenance_type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, default="NORMAL")
    symptoms = models.TextField()
    diagnosis = models.TextField(blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    abandoned_at = models.DateTimeField(null=True, blank=True)
    abandoned_reason = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="opened_orders")
    technician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="assigned_orders")
    final_tests = models.TextField(blank=True)
    released = models.BooleanField(default=False)
    labor_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    parts_used = models.TextField(blank=True)

    class Meta:
        ordering = ("-opened_at",)

    def save(self, *args, **kwargs):
        if not self.number:
            prefix = self.opened_at.strftime("%Y") if self.opened_at else "OS"
            self.number = f"OS-{prefix}-{str(self.public_id)[:8].upper()}"
        now = timezone.now()
        if self.status == self.Status.IN_PROGRESS and not self.started_at:
            self.started_at = now
        if self.status == self.Status.ABANDONED:
            self.abandoned_at = self.abandoned_at or now
            self.closed_at = None
            self.released = False
        else:
            self.abandoned_at = None
            self.abandoned_reason = ""
            if self.status in {self.Status.COMPLETED, self.Status.CANCELLED}:
                self.closed_at = self.closed_at or now
            else:
                self.closed_at = None
        super().save(*args, **kwargs)

    def clean(self):
        if self.status in {self.Status.IN_PROGRESS, self.Status.WAITING_PARTS, self.Status.ABANDONED} and not self.technician_id:
            raise ValidationError("A etapa informada exige um técnico responsável.")
        if self.status == self.Status.ABANDONED and not self.abandoned_reason.strip():
            raise ValidationError("Informe o motivo do abandono do chamado.")
        if self.released and (self.status != self.Status.COMPLETED or not self.final_tests.strip() or not self.technician_id):
            raise ValidationError("A liberação exige OS concluída, testes finais e técnico responsável.")


class MaintenanceActivity(models.Model):
    service_order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name="activities")
    description = models.TextField()
    hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    part_used = models.CharField(max_length=180, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
