from django.db import migrations, models


def backfill_estimated_freight(apps, schema_editor):
    RentalQuote = apps.get_model("rentals", "RentalQuote")
    RentalQuote.objects.update(estimated_transport_fee=models.F("transport_fee"))


class Migration(migrations.Migration):
    dependencies = [("rentals", "0009_rentalquote_requested_delivery")]

    operations = [
        migrations.AddField(
            model_name="rentalquote",
            name="estimated_transport_fee",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="rentalquote",
            name="transport_fee_adjustment_reason",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(backfill_estimated_freight, migrations.RunPython.noop),
    ]
