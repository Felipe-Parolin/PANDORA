import uuid
from django.db import models


class Customer(models.Model):
    class PersonType(models.TextChoices):
        INDIVIDUAL = "PF", "Pessoa física"
        COMPANY = "PJ", "Pessoa jurídica"

    person_type = models.CharField(max_length=2, choices=PersonType.choices)
    name = models.CharField(max_length=180)
    document = models.CharField(max_length=18, unique=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=24)
    address = models.CharField(max_length=255, blank=True)
    address_cep = models.CharField(max_length=8, blank=True, default="")
    address_number = models.CharField(max_length=20, blank=True, default="")
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    marketing_opt_in = models.BooleanField(default=False, help_text="Cliente autorizou receber comunicações comerciais por e-mail.")
    marketing_unsubscribe_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name
