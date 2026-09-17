from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .acl import PERMISSION_CATALOG, VALID_PERMISSIONS
from .models import AccessGroup, User


class AccessGroupSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = AccessGroup
        fields = ("id", "name", "description", "permissions", "is_system", "user_count", "created_at", "updated_at")
        read_only_fields = ("is_system", "created_at", "updated_at")

    def validate_permissions(self, value):
        invalid = set(value).difference(VALID_PERMISSIONS | {"*"})
        if invalid:
            raise serializers.ValidationError(f"Permissões inválidas: {', '.join(sorted(invalid))}")
        if "*" in value and len(value) > 1:
            return ["*"]
        return sorted(set(value))


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    access_group_name = serializers.CharField(source="access_group.name", read_only=True)
    permissions = serializers.ListField(source="acl_permissions", read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "phone", "role", "role_label", "access_group", "access_group_name", "permissions", "is_active", "password")

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save(update_fields=["password"])
        return instance


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data
