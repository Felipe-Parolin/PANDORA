from django.contrib import admin
from .models import MaintenanceActivity, MaintenancePlan, ServiceOrder

admin.site.register((MaintenancePlan, ServiceOrder, MaintenanceActivity))
