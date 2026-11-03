from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("logistics", "0003_transporttask_schedule_load")]

    operations = [
        migrations.AddField(
            model_name="transporttask",
            name="load_manifest",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
