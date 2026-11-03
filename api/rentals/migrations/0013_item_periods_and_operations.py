from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_periods(apps, schema_editor):
    Item = apps.get_model("rentals", "RentalItem")
    for item in Item.objects.select_related("quote").iterator():
        quote = item.quote
        item.start_date, item.end_date = quote.start_date, quote.end_date
        item.stage = {"ACTIVE": "DELIVERED", "RETURNED": "RETURNED", "COMPLETED": "COMPLETED"}.get(quote.status, "PENDING")
        item.delivered_at, item.delivered_by_id = quote.delivered_at, quote.delivered_by_id
        item.returned_at, item.returned_by_id = quote.returned_at, quote.returned_by_id
        item.delivery_conditions, item.return_conditions = quote.delivery_conditions, quote.return_conditions
        # O estado histórico é preservado sem inventar datas que não foram registradas.
        item.save()


class Migration(migrations.Migration):
    dependencies = [("rentals", "0012_rental_requested_return"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="rentalitem", name="start_date", field=models.DateField(null=True)),
        migrations.AddField(model_name="rentalitem", name="end_date", field=models.DateField(null=True)),
        migrations.AddField(model_name="rentalitem", name="stage", field=models.CharField(choices=[("PENDING", "A retirar"), ("DELIVERED", "Com o cliente"), ("RETURNED", "Em inspeção de retorno"), ("COMPLETED", "Devolução concluída")], default="PENDING", max_length=16)),
        *[migrations.AddField(model_name="rentalitem", name=name, field=models.DateTimeField(blank=True, null=True)) for name in ("delivered_at", "returned_at", "finalized_at")],
        *[migrations.AddField(model_name="rentalitem", name=name, field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)) for name in ("delivered_by", "returned_by")],
        *[migrations.AddField(model_name="rentalitem", name=name, field=models.TextField(blank=True)) for name in ("delivery_conditions", "return_conditions")],
        migrations.AddField(model_name="rentalextension", name="item_changes", field=models.JSONField(blank=True, default=list)),
        migrations.RunPython(copy_periods, migrations.RunPython.noop),
        migrations.AlterField(model_name="rentalitem", name="start_date", field=models.DateField()),
        migrations.AlterField(model_name="rentalitem", name="end_date", field=models.DateField()),
        migrations.AddConstraint(model_name="rentalitem", constraint=models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="rental_item_valid_period")),
    ]
