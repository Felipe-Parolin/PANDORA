# Encerramento de sugestões de aquisição aceitas (comprada / descartada).
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0002_ai_recommendations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="airecommendation",
            name="status",
            field=models.CharField(choices=[("PENDING", "Pendente"), ("ACCEPTED", "Aceita"), ("REJECTED", "Rejeitada"), ("POSTPONED", "Adiada"), ("PURCHASED", "Comprada"), ("DISCARDED", "Descartada")], default="PENDING", max_length=12),
        ),
        migrations.AddField(
            model_name="airecommendation",
            name="closed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="closed_ai_recommendations", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="airecommendation",
            name="closure_note",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="airecommendation",
            name="closed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
