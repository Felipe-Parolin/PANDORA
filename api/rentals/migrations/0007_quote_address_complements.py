from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rentals", "0006_quote_cep_and_percentage_discount"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentalquote",
            name="delivery_complement",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="rentalquote",
            name="return_complement",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
