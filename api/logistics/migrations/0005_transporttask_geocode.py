from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0004_transporttask_load_manifest"),
    ]

    operations = [
        migrations.AddField(model_name="transporttask", name="latitude", field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="transporttask", name="longitude", field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="transporttask", name="geocoded_address", field=models.CharField(blank=True, max_length=255)),
    ]
