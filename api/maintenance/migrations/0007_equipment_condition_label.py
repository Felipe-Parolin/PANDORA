from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0006_serviceorder_equipment_condition")]
    operations = [
        migrations.AlterField(
            model_name="serviceorder", name="equipment_condition",
            field=models.CharField(choices=[("PENDING", "A avaliar"), ("OPERATING", "Operante"), ("BROKEN", "Inoperante")], default="PENDING", max_length=12),
        ),
    ]
