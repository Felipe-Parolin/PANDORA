from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("assets", "0004_mediaasset_rental_inspection")]
    operations = [
        migrations.AddField(
            model_name="equipmentcategory",
            name="parent",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="subcategories", to="assets.equipmentcategory"),
        ),
    ]
