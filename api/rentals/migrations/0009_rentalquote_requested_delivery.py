from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('rentals', '0008_backfill_return_service_orders')]
    operations = [
        migrations.AddField(model_name='rentalquote', name='requested_delivery_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='rentalquote', name='requested_delivery_notes', field=models.TextField(blank=True)),
    ]
