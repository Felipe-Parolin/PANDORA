from django.contrib import admin
from .models import RentalItem, RentalQuote

admin.site.register((RentalQuote, RentalItem))
