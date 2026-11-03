# Generated for PANDORA: central de recomendações e registro de demanda não atendida.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0001_initial"),
        ("assets", "0004_mediaasset_rental_inspection"),
        ("maintenance", "0004_serviceorder_plan_due_date_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AIRecommendation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("PREVENTIVE_MAINTENANCE", "Manutenção preventiva"), ("EQUIPMENT_PURCHASE", "Aquisição de equipamento")], max_length=32)),
                ("status", models.CharField(choices=[("PENDING", "Pendente"), ("ACCEPTED", "Aceita"), ("REJECTED", "Rejeitada"), ("POSTPONED", "Adiada")], default="PENDING", max_length=12)),
                ("title", models.CharField(max_length=200)),
                ("summary", models.TextField()),
                ("rationale", models.TextField(blank=True)),
                ("priority", models.CharField(default="MEDIUM", max_length=12)),
                ("evidence", models.JSONField(blank=True, default=list)),
                ("suggested_payload", models.JSONField(blank=True, default=dict)),
                ("estimated_recoverable_revenue", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("estimated_purchase_cost", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("estimated_monthly_benefit", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("payback_months", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("decision_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("decided_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="decided_ai_recommendations", to=settings.AUTH_USER_MODEL)),
                ("equipment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ai_recommendations", to="assets.equipment")),
                ("generated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="generated_ai_recommendations", to=settings.AUTH_USER_MODEL)),
                ("service_order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ai_recommendations", to="maintenance.serviceorder")),
            ],
            options={"ordering": ("status", "-created_at")},
        ),
        migrations.CreateModel(
            name="UnfulfilledDemand",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requested_days", models.PositiveIntegerField(default=1)),
                ("expected_daily_rate", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("requested_at", models.DateField()),
                ("reason", models.CharField(choices=[("UNAVAILABLE", "Sem unidade disponível"), ("MAINTENANCE", "Equipamento em manutenção"), ("FLEET_CAPACITY", "Capacidade insuficiente da frota"), ("OTHER", "Outro motivo")], default="UNAVAILABLE", max_length=24)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("equipment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="unfulfilled_demands", to="assets.equipment")),
                ("recorded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recorded_unfulfilled_demands", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-requested_at", "-id")},
        ),
        migrations.AddIndex(model_name="airecommendation", index=models.Index(fields=["kind", "status"], name="ai_airecomm_kind_5a1c4f_idx")),
        migrations.AddIndex(model_name="airecommendation", index=models.Index(fields=["equipment", "created_at"], name="ai_airecomm_equipme_0a9d4b_idx")),
    ]
