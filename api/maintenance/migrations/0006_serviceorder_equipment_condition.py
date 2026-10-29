from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0005_serviceorder_costs")]
    operations = [
        migrations.AddField(
            model_name="serviceorder",
            name="equipment_condition",
            field=models.CharField(choices=[("PENDING", "A avaliar"), ("OPERATING", "Operante"), ("BROKEN", "Quebrado")], default="PENDING", max_length=12),
        ),
    ]
