from django.db.models import Count
from rest_framework.decorators import action
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.views import TokenObtainPairView

from .acl import PERMISSION_CATALOG
from .models import AccessGroup, User
from .permissions import ACLPermission
from .serializers import AccessGroupSerializer, EmailTokenObtainPairSerializer, UserSerializer


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class CurrentUserView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class UserViewSet(ModelViewSet):
    queryset = User.objects.order_by("full_name")
    serializer_class = UserSerializer
    search_fields = ("full_name", "email")

    permission_classes = [ACLPermission]
    acl_view = "accounts.users.view"
    acl_manage = "accounts.users.manage"

    def get_queryset(self):
        queryset = super().get_queryset()
        role = self.request.query_params.get("role")
        active = self.request.query_params.get("active")
        if role:
            queryset = queryset.filter(role=role)
        if active in {"true", "false"}:
            queryset = queryset.filter(is_active=active == "true")
        return queryset


class AccessGroupViewSet(ModelViewSet):
    queryset = AccessGroup.objects.annotate(user_count=Count("users", distinct=True))
    serializer_class = AccessGroupSerializer
    permission_classes = [ACLPermission]
    acl_view = ("accounts.groups.manage", "accounts.users.manage")
    acl_manage = "accounts.groups.manage"

    @action(detail=False, methods=["get"])
    def catalog(self, request):
        return Response(PERMISSION_CATALOG)

    def perform_destroy(self, instance):
        if instance.is_system:
            raise ValidationError("Os grupos padrão não podem ser excluídos, mas suas permissões podem ser ajustadas.")
        if instance.users.exists():
            raise ValidationError("Transfira os usuários deste grupo antes de excluí-lo.")
        instance.delete()
