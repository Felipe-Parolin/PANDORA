from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("customers", "0003_customer_marketing_unsubscribe_token")]

    operations = [
        migrations.AddField(
            model_name="customer", name="address_cep",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
    ]
