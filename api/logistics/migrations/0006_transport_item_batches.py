from django.db import migrations, models


def copy_batches(apps, schema_editor):
    Task = apps.get_model("logistics", "TransportTask")
    for task in Task.objects.select_related("quote").iterator():
        task.batch_date = task.quote.start_date if task.leg == "DELIVERY" else task.quote.end_date
        task.batch_key = f"{task.batch_date}:1"
        task.items_scoped = True
        task.save(update_fields=("batch_date", "batch_key", "items_scoped"))
        task.rental_items.set(task.quote.items.all())


class Migration(migrations.Migration):
    dependencies = [("logistics", "0005_transporttask_geocode"), ("rentals", "0013_item_periods_and_operations")]
    operations = [
        migrations.RemoveConstraint(model_name="transporttask", name="unique_quote_transport_leg"),
        migrations.AddField(model_name="transporttask", name="rental_items", field=models.ManyToManyField(blank=True, related_name="transport_tasks", to="rentals.rentalitem")),
        migrations.AddField(model_name="transporttask", name="items_scoped", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="transporttask", name="batch_date", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="transporttask", name="batch_key", field=models.CharField(blank=True, default="", max_length=48)),
        migrations.RunPython(copy_batches, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="transporttask", constraint=models.UniqueConstraint(fields=("quote", "leg", "batch_key"), name="unique_quote_transport_batch")),
    ]
