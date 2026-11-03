from django.db import migrations, models


def copy_cep(apps, schema_editor):
    Task = apps.get_model("logistics", "TransportTask")
    for task in Task.objects.select_related("quote").iterator():
        task.address_cep = task.quote.delivery_cep if task.leg == "DELIVERY" else task.quote.return_cep
        task.save(update_fields=("address_cep",))


class Migration(migrations.Migration):
    dependencies = [("logistics", "0006_transport_item_batches"), ("rentals", "0014_item_destinations")]
    operations = [migrations.AddField(model_name="transporttask", name="address_cep", field=models.CharField(blank=True, default="", max_length=8)),
                  migrations.RunPython(copy_cep, migrations.RunPython.noop)]
