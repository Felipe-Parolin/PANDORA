from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    entity = models.CharField(max_length=80)
    record_id = models.CharField(max_length=80)
    action = models.CharField(max_length=80)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class Notification(models.Model):
    class Kind(models.TextChoices):
        RENTAL = "RENTAL", "Locação"
        MAINTENANCE = "MAINTENANCE", "Manutenção"
        TRANSPORT = "TRANSPORT", "Transporte"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    title = models.CharField(max_length=180)
    message = models.CharField(max_length=300)
    target_url = models.CharField(max_length=240)
    event_key = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("recipient", "event_key"), name="unique_notification_recipient_event")]
