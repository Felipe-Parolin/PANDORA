from django.contrib.auth.models import Group
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def ensure_default_groups(sender, **kwargs):
    if sender.name == "accounts":
        from .acl import DEFAULT_GROUPS
        from .models import AccessGroup, User

        for name in ("Administrador", "Vendedor", "Manutenção"):
            Group.objects.get_or_create(name=name)
        for role, defaults in DEFAULT_GROUPS.items():
            group, _ = AccessGroup.objects.get_or_create(
                name=defaults["name"],
                defaults={
                    "description": defaults["description"],
                    "permissions": defaults["permissions"],
                    "is_system": True,
                },
            )
            User.objects.filter(role=role, access_group__isnull=True).update(access_group=group)
