from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('logistics', '0002_transporttask_complement')]
    operations = [
        migrations.AddField(model_name='transporttask', name='scheduled_end_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='transporttask', name='trip_reference', field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name='transporttask', name='load_sequence', field=models.PositiveSmallIntegerField(default=1)),
    ]
