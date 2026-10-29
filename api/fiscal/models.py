from django.db import models


class FiscalAddress(models.Model):
    postal_code = models.CharField(max_length=8, blank=True)
    street = models.CharField(max_length=150, blank=True)
    number = models.CharField(max_length=20, blank=True)
    complement = models.CharField(max_length=120, blank=True)
    neighborhood = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    municipality_code = models.CharField(max_length=7, blank=True)

    class Meta:
        abstract = True


class ICMSTaxpayer(models.TextChoices):
    UNKNOWN = "UNKNOWN", "A confirmar"
    CONTRIBUTOR = "CONTRIBUTOR", "Contribuinte do ICMS"
    EXEMPT = "EXEMPT", "Contribuinte isento de inscrição"
    NON_CONTRIBUTOR = "NON_CONTRIBUTOR", "Não contribuinte do ICMS"


class FiscalCompany(FiscalAddress):
    """One configurable issuer per installation; contains no provider secrets."""

    class TaxRegime(models.TextChoices):
        UNKNOWN = "UNKNOWN", "A confirmar"
        SIMPLE = "SIMPLE", "Simples Nacional"
        MEI = "MEI", "MEI"
        PRESUMED = "PRESUMED", "Lucro Presumido"
        REAL = "REAL", "Lucro Real"

    legal_name = models.CharField(max_length=180, blank=True)
    trade_name = models.CharField(max_length=150, blank=True)
    cnpj = models.CharField(max_length=14, blank=True)
    tax_regime = models.CharField(max_length=16, choices=TaxRegime.choices, default=TaxRegime.UNKNOWN)
    icms_status = models.CharField(max_length=20, choices=ICMSTaxpayer.choices, default=ICMSTaxpayer.UNKNOWN)
    state_registration = models.CharField(max_length=30, blank=True)
    municipal_registration = models.CharField(max_length=30, blank=True)
    cnae = models.CharField(max_length=7, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=24, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class FiscalCustomerData(FiscalAddress):
    customer = models.OneToOneField("customers.Customer", on_delete=models.CASCADE, related_name="fiscal_data")
    icms_status = models.CharField(max_length=20, choices=ICMSTaxpayer.choices, default=ICMSTaxpayer.UNKNOWN)
    state_registration = models.CharField(max_length=30, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class FiscalEquipmentData(models.Model):
    equipment = models.OneToOneField("assets.Equipment", on_delete=models.CASCADE, related_name="fiscal_data")
    ncm = models.CharField(max_length=8, blank=True)
    asset_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
