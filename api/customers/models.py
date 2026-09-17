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
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name
