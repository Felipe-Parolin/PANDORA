from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rentals", "0009_documents_unmet_demand")]

    operations = [
        migrations.AddField(
            model_name="rentalquote",
            name="transport_estimate",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
