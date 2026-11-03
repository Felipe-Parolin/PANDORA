import uuid
from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('customers', '0002_customer_marketing_opt_in')]
    operations = [migrations.AddField(model_name='customer', name='marketing_unsubscribe_token', field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True))]
