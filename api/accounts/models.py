from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from .acl import DEFAULT_GROUPS


class AccessGroup(models.Model):
    name = models.CharField("nome", max_length=100, unique=True)
    description = models.TextField("descrição", blank=True)
    permissions = models.JSONField("permissões", default=list, blank=True)
    is_system = models.BooleanField("grupo do sistema", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        SALES = "SALES", "Vendedor"
        MAINTENANCE = "MAINTENANCE", "Manutenção"

    username = None
    email = models.EmailField("e-mail", unique=True)
    full_name = models.CharField("nome completo", max_length=180)
    phone = models.CharField("telefone", max_length=24, blank=True)
    role = models.CharField("perfil", max_length=20, choices=Role.choices, default=Role.SALES)
    access_group = models.ForeignKey(
        AccessGroup,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.full_name or self.email

    @property
    def acl_permissions(self):
        if self.is_superuser:
            return ["*"]
        if self.access_group_id:
            return list(self.access_group.permissions or [])
        return list(DEFAULT_GROUPS.get(self.role, {}).get("permissions", []))

    def has_acl(self, permission):
        permissions = self.acl_permissions
        return "*" in permissions or permission in permissions
