from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logistics", "0001_initial"),
        ("rentals", "0007_quote_address_complements"),
    ]

    operations = [
        migrations.AddField(
            model_name="transporttask",
            name="complement",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
