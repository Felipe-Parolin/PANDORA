from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rentals", "0013_item_periods_and_operations")]
    operations = [
        migrations.AddField(model_name="rentalquote", name="delivery_number", field=models.CharField(blank=True, default="", max_length=20)),
        migrations.AddField(model_name="rentalquote", name="return_number", field=models.CharField(blank=True, default="", max_length=20)),
        migrations.AddField(model_name="rentalitem", name="delivery_location", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="rentalitem", name="return_location", field=models.JSONField(blank=True, default=dict)),
    ]
