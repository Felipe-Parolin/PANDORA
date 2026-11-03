from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from accounts.permissions import ACLPermission
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [ACLPermission]
    acl_view = "customers.view"
    acl_manage = "customers.manage"

    @action(detail=False, methods=["get"], url_path="lookup-address")
    def lookup_address(self, request):
        if not request.user.has_acl("customers.manage"):
            raise PermissionDenied("Seu grupo não possui permissão para cadastrar endereços.")
        from rentals.freight import lookup_cep
        return Response(lookup_cep(request.query_params.get("cep")))

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search) | queryset.filter(document__icontains=search)
        return queryset
