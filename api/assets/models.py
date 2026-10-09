import uuid
from django.core.validators import FileExtensionValidator
from django.db import models


def validate_file_size(value):
    if value.size > 10 * 1024 * 1024:
        from django.core.exceptions import ValidationError
        raise ValidationError("O arquivo deve ter no máximo 10 MB.")


class EquipmentCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    default_daily_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pre_rental_checklist = models.JSONField(default=list, blank=True)
    return_checklist = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name_plural = "equipment categories"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Equipment(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Disponível"
        RESERVED = "RESERVED", "Reservado"
        RENTED = "RENTED", "Locado"
        MAINTENANCE = "MAINTENANCE", "Em manutenção"
        INSPECTION = "INSPECTION", "Em inspeção"
        INACTIVE = "INACTIVE", "Inativo"

    category = models.ForeignKey(EquipmentCategory, on_delete=models.PROTECT, related_name="equipment")
    name = models.CharField(max_length=150)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=120, unique=True)
    internal_code = models.CharField(max_length=40, unique=True)
    qr_code_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    daily_rate = models.DecimalField(max_digits=12, decimal_places=2)
    acquisition_date = models.DateField(null=True, blank=True)
    technical_details = models.TextField(blank=True)
    current_usage_hours = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name", "internal_code")

    def __str__(self):
        return f"{self.internal_code} - {self.name}"


class MediaAsset(models.Model):
    class Category(models.TextChoices):
        PHOTO = "PHOTO", "Foto"
        MANUAL = "MANUAL", "Manual"
        DOCUMENT = "DOCUMENT", "Documento"
        INSPECTION = "INSPECTION", "Evidência de inspeção"
        SERVICE = "SERVICE", "Evidência de manutenção"
        OTHER = "OTHER", "Outro"

    name = models.CharField(max_length=180)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="pandora/%Y/%m/", validators=[validate_file_size, FileExtensionValidator(["pdf", "png", "jpg", "jpeg", "webp", "doc", "docx"])] )
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="media", null=True, blank=True)
    service_order = models.ForeignKey("maintenance.ServiceOrder", on_delete=models.CASCADE, related_name="media", null=True, blank=True)
    rental_quote = models.ForeignKey("rentals.RentalQuote", on_delete=models.CASCADE, related_name="media", null=True, blank=True)
    rental_inspection = models.ForeignKey("rentals.RentalInspection", on_delete=models.CASCADE, related_name="media", null=True, blank=True)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="uploaded_media")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name
