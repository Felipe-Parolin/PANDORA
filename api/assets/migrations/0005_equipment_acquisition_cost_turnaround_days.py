from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("assets", "0004_mediaasset_rental_inspection")]

    operations = [
        migrations.AddField(model_name="equipment", name="acquisition_cost", field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
        migrations.AddField(model_name="equipment", name="turnaround_days", field=models.PositiveSmallIntegerField(default=0)),
    ]
