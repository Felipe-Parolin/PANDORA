from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('assets', '0005_equipmentcategory_parent')]
    operations = [migrations.AddField(model_name='equipment', name='estimated_weight_kg', field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True))]
