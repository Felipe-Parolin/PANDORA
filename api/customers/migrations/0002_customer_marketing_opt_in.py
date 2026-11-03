from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('customers', '0001_initial')]
    operations = [migrations.AddField(model_name='customer', name='marketing_opt_in', field=models.BooleanField(default=False, help_text='Cliente autorizou receber comunicações comerciais por e-mail.'))]
