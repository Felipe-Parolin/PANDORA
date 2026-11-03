"""Limpeza local explícita. Não é exposta pela API nem executada ao iniciar o sistema."""
from django.apps import apps
from django.contrib.auth.models import Group
from django.core.management.base import CommandError
from django.db import connection, transaction

from accounts.models import AccessGroup, User

DOMAIN_APPS = {"assets", "customers", "maintenance", "rentals", "logistics", "ai", "commercial", "core", "sessions", "admin"}


def ensure_local_database():
    if connection.vendor != "postgresql" or connection.settings_dict.get("HOST", "") not in {"", "localhost", "127.0.0.1", "::1"}:
        raise CommandError("A limpeza aceita somente PostgreSQL no próprio computador.")


def data_models():
    return [model for model in apps.get_models(include_auto_created=True) if model._meta.app_label in DOMAIN_APPS and model._meta.managed and not model._meta.proxy]


def validate_admin(keep_user):
    admin = User.objects.select_related("access_group").get(pk=keep_user)
    if not admin.is_active or not admin.has_usable_password() or "*" not in admin.acl_permissions:
        raise CommandError("O usuário preservado precisa estar ativo, ter senha e acesso de administrador.")
    return admin


def reset_counts():
    tables = set(connection.introspection.table_names())
    if any(model._meta.db_table not in tables for model in data_models()):
        raise CommandError("Há tabelas pendentes. Execute migrate antes da simulação ou limpeza.")
    return {model._meta.label: model.objects.count() for model in data_models()}


@transaction.atomic
def reset_local_data(keep_user):
    ensure_local_database()
    User.objects.select_for_update().get(pk=keep_user)
    admin = validate_admin(keep_user)
    credentials = (admin.password, admin.access_group_id, admin.acl_permissions)
    models = data_models()
    tables = sorted({model._meta.db_table for model in models})
    # Sem CASCADE: uma FK de aplicação não prevista interrompe tudo e preserva o banco.
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE " + ", ".join(connection.ops.quote_name(table) for table in tables) + " RESTART IDENTITY")
    User.objects.exclude(pk=admin.pk).delete()
    AccessGroup.objects.exclude(pk=admin.access_group_id).delete()
    Group.objects.exclude(pk__in=admin.groups.values("pk")).delete()
    admin.refresh_from_db()
    admin = validate_admin(keep_user)
    if User.objects.count() != 1 or (admin.password, admin.access_group_id, admin.acl_permissions) != credentials or any(model.objects.exists() for model in models):
        raise CommandError("A verificação da limpeza falhou. A transação foi revertida.")
    return {"users": 1, "admin_id": admin.pk, "cleared_tables": len(tables)}
