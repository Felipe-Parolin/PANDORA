from rest_framework.viewsets import ModelViewSet
from accounts.permissions import ACLPermission
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [ACLPermission]
    acl_view = "customers.view"
    acl_manage = "customers.manage"

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search) | queryset.filter(document__icontains=search)
        return queryset
