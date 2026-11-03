from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("customers", "0004_customer_address_cep")]
    operations = [migrations.AddField(model_name="customer", name="address_number", field=models.CharField(blank=True, default="", max_length=20))]
