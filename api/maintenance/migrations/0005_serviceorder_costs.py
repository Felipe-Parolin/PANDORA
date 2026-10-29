from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0004_serviceorder_plan_due_date_and_more")]

    operations = [
        migrations.AddField(model_name="serviceorder", name="labor_cost", field=models.DecimalField(decimal_places=2, default=0, max_digits=12)),
        migrations.AddField(model_name="serviceorder", name="parts_cost", field=models.DecimalField(decimal_places=2, default=0, max_digits=12)),
    ]
