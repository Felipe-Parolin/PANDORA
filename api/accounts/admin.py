from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import AccessGroup, User


@admin.register(User)
class PandoraUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "is_active")
    fieldsets = ((None, {"fields": ("email", "password")}), ("Dados", {"fields": ("full_name", "phone", "role")}), ("Acesso", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}))
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "full_name", "role", "password1", "password2")}),)
    search_fields = ("email", "full_name")


admin.site.register(AccessGroup)
