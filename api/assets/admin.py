from django.contrib import admin
from .models import Equipment, EquipmentCategory, MediaAsset

admin.site.register((EquipmentCategory, Equipment, MediaAsset))
