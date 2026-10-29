import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("assets", "0005_equipment_acquisition_cost_turnaround_days"),
        ("customers", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FiscalCompany",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("postal_code", models.CharField(blank=True, max_length=8)),
                ("street", models.CharField(blank=True, max_length=150)),
                ("number", models.CharField(blank=True, max_length=20)),
                ("complement", models.CharField(blank=True, max_length=120)),
                ("neighborhood", models.CharField(blank=True, max_length=100)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("state", models.CharField(blank=True, max_length=2)),
                ("municipality_code", models.CharField(blank=True, max_length=7)),
                ("legal_name", models.CharField(blank=True, max_length=180)),
                ("trade_name", models.CharField(blank=True, max_length=150)),
                ("cnpj", models.CharField(blank=True, max_length=14)),
                ("tax_regime", models.CharField(choices=[("UNKNOWN", "A confirmar"), ("SIMPLE", "Simples Nacional"), ("MEI", "MEI"), ("PRESUMED", "Lucro Presumido"), ("REAL", "Lucro Real")], default="UNKNOWN", max_length=16)),
                ("icms_status", models.CharField(choices=[("UNKNOWN", "A confirmar"), ("CONTRIBUTOR", "Contribuinte do ICMS"), ("EXEMPT", "Contribuinte isento de inscrição"), ("NON_CONTRIBUTOR", "Não contribuinte do ICMS")], default="UNKNOWN", max_length=20)),
                ("state_registration", models.CharField(blank=True, max_length=30)),
                ("municipal_registration", models.CharField(blank=True, max_length=30)),
                ("cnae", models.CharField(blank=True, max_length=7)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=24)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="FiscalCustomerData",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("postal_code", models.CharField(blank=True, max_length=8)),
                ("street", models.CharField(blank=True, max_length=150)),
                ("number", models.CharField(blank=True, max_length=20)),
                ("complement", models.CharField(blank=True, max_length=120)),
                ("neighborhood", models.CharField(blank=True, max_length=100)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("state", models.CharField(blank=True, max_length=2)),
                ("municipality_code", models.CharField(blank=True, max_length=7)),
                ("icms_status", models.CharField(choices=[("UNKNOWN", "A confirmar"), ("CONTRIBUTOR", "Contribuinte do ICMS"), ("EXEMPT", "Contribuinte isento de inscrição"), ("NON_CONTRIBUTOR", "Não contribuinte do ICMS")], default="UNKNOWN", max_length=20)),
                ("state_registration", models.CharField(blank=True, max_length=30)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="fiscal_data", to="customers.customer")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="FiscalEquipmentData",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ncm", models.CharField(blank=True, max_length=8)),
                ("asset_value", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("equipment", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="fiscal_data", to="assets.equipment")),
            ],
        ),
    ]
