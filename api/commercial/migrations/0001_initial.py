import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('assets', '0005_equipmentcategory_parent'),
        ('accounts', '0003_logistics_permissions'),
        ('customers', '0001_initial'),
    ]
    operations = [
        migrations.CreateModel(name='EquipmentPackage', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(max_length=140, unique=True)), ('description', models.TextField(blank=True)),
            ('image_url', models.URLField(blank=True)), ('active', models.BooleanField(default=True)),
            ('promotional_discount_percent', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
            ('rental_days_default', models.PositiveIntegerField(default=1)),
            ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
            ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='packages', to='assets.equipmentcategory')),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_equipment_packages', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ('name',)}),
        migrations.CreateModel(name='MarketingCampaign', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('title', models.CharField(max_length=160)), ('subject', models.CharField(max_length=180)), ('body_html', models.TextField()),
            ('status', models.CharField(choices=[('DRAFT','Rascunho'),('READY','Pronta para envio'),('SENT','Enviada'),('FAILED','Falha'),('PARTIAL','Parcialmente enviada')], default='DRAFT', max_length=10)),
            ('scheduled_at', models.DateTimeField(blank=True, null=True)), ('sent_at', models.DateTimeField(blank=True, null=True)),
            ('recipient_count', models.PositiveIntegerField(default=0)), ('result_log', models.JSONField(blank=True, default=list)), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='marketing_campaigns', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ('-created_at',)}),
        migrations.CreateModel(name='PurchaseRecommendation', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('status', models.CharField(choices=[('PENDING','Pendente de análise'),('APPROVED','Aprovada'),('REJECTED','Rejeitada'),('ACQUIRED','Já adquirida')], default='PENDING', max_length=12)),
            ('priority', models.CharField(default='MEDIUM', max_length=10)), ('current_total', models.PositiveIntegerField(default=0)),
            ('current_available', models.PositiveIntegerField(default=0)), ('demand_events', models.PositiveIntegerField(default=0)),
            ('maintenance_orders', models.PositiveIntegerField(default=0)), ('unavailable_days', models.DecimalField(decimal_places=2, default=0, max_digits=9)),
            ('suggested_quantity', models.PositiveSmallIntegerField(default=1)), ('evidence', models.JSONField(blank=True, default=dict)),
            ('rationale', models.TextField()), ('decision_note', models.TextField(blank=True)), ('decided_at', models.DateTimeField(blank=True, null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
            ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchase_recommendations', to='assets.equipmentcategory')),
            ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='purchase_decisions', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ('-created_at',)}),
        migrations.CreateModel(name='EquipmentPackageComponent', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('quantity', models.PositiveSmallIntegerField()), ('reference_daily_rate', models.DecimalField(decimal_places=2, max_digits=12)),
            ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='package_components', to='assets.equipmentcategory')),
            ('package', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='components', to='commercial.equipmentpackage')),
        ], options={'ordering': ('category__name',)}),
        migrations.AddConstraint(model_name='equipmentpackagecomponent', constraint=models.UniqueConstraint(fields=('package','category'), name='unique_package_category')),
        migrations.AddConstraint(model_name='purchaserecommendation', constraint=models.UniqueConstraint(condition=models.Q(status='PENDING'), fields=('category',), name='unique_pending_purchase_rec_category')),
    ]
