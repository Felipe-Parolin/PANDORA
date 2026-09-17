from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="serviceorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("OPEN", "Aberta"),
                    ("SCHEDULED", "Agendada"),
                    ("IN_PROGRESS", "Em execução"),
                    ("WAITING_PARTS", "Aguardando peças"),
                    ("ABANDONED", "Abandonada"),
                    ("COMPLETED", "Concluída"),
                    ("CANCELLED", "Cancelada"),
                ],
                default="OPEN",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="serviceorder",
            name="abandoned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="serviceorder",
            name="abandoned_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="serviceorder",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
