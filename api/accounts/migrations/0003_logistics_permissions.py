from django.db import migrations


def add_system_permissions(apps, schema_editor):
    AccessGroup = apps.get_model("accounts", "AccessGroup")
    additions = {
        "Vendedor": ("logistics.view", "logistics.manage"),
        "Manutenção": ("logistics.view",),
    }
    for name, codes in additions.items():
        group = AccessGroup.objects.filter(name=name, is_system=True).first()
        if group and "*" not in group.permissions:
            permissions = list(group.permissions or [])
            for code in codes:
                if code not in permissions:
                    permissions.append(code)
            group.permissions = permissions
            group.save(update_fields=("permissions",))


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_accessgroup_user_access_group")]

    operations = [migrations.RunPython(add_system_permissions, migrations.RunPython.noop)]
