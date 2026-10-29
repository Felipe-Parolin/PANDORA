import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0005_equipment_acquisition_cost_turnaround_days"),
        ("customers", "0001_initial"),
        ("rentals", "0008_backfill_return_service_orders"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RentalDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("QUOTE", "Orçamento"), ("DELIVERY", "Comprovante de entrega"), ("RETURN", "Comprovante de devolução")], max_length=12)),
                ("version", models.PositiveIntegerField()),
                ("snapshot", models.JSONField()),
                ("content_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rental_documents", to=settings.AUTH_USER_MODEL)),
                ("quote", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="documents", to="rentals.rentalquote")),
            ],
            options={"ordering": ("kind", "-version")},
        ),
        migrations.CreateModel(
            name="UnmetRentalDemand",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("reason", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="unmet_rental_demands", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="unmet_rental_demands", to="customers.customer")),
                ("equipment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="unmet_demands", to="assets.equipment")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(model_name="rentaldocument", constraint=models.UniqueConstraint(fields=("quote", "kind", "version"), name="unique_rental_document_version")),
        migrations.AddConstraint(model_name="unmetrentaldemand", constraint=models.UniqueConstraint(fields=("equipment", "customer", "start_date", "end_date"), name="unique_unmet_rental_demand")),
    ]
