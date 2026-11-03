import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0006_equipment_estimated_weight"),
        ("customers", "0003_customer_marketing_unsubscribe_token"),
        ("ai", "0003_recommendation_closure"),
    ]

    operations = [
        migrations.AlterField(
            model_name="unfulfilleddemand",
            name="equipment",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="unfulfilled_demands", to="assets.equipment"),
        ),
        migrations.AddField(
            model_name="unfulfilleddemand",
            name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="unfulfilled_demands", to="assets.equipmentcategory"),
        ),
        migrations.AddField(
            model_name="unfulfilleddemand",
            name="requested_item",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="unfulfilleddemand",
            name="customer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="unfulfilled_demands", to="customers.customer"),
        ),
        migrations.AddField(
            model_name="unfulfilleddemand",
            name="quantity",
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
