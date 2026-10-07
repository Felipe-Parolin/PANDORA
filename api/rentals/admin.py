from django.contrib import admin
from .models import RentalExtension, RentalInspection, RentalItem, RentalQuote

admin.site.register((RentalQuote, RentalItem, RentalInspection, RentalExtension))
