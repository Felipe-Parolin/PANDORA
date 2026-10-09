from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rentals", "0005_rentalquote_delivery_address_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentalquote",
            name="delivery_cep",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AddField(
            model_name="rentalquote",
            name="return_cep",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AddField(
            model_name="rentalquote",
            name="discount_percent",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
    ]
