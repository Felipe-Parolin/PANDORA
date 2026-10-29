from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from accounts.permissions import ACLPermission
from assets.models import Equipment
from core.models import AuditLog
from customers.models import Customer
from rentals.models import RentalQuote
from .models import FiscalCompany, FiscalCustomerData, FiscalEquipmentData
from .serializers import FiscalCompanySerializer, FiscalCustomerDataSerializer, FiscalEquipmentDataSerializer
from .services import company_data, prepare_rental


def audit_patch(request, instance):
    AuditLog.objects.create(user=request.user, entity=type(instance).__name__, record_id=str(instance.pk),
                            action="FISCAL_DATA_UPDATED", data={"fields": list(request.data.keys())})


class FiscalCompanyView(APIView):
    permission_classes = [ACLPermission]
    acl_view = "fiscal.view"
    acl_manage = "fiscal.configure"

    def get(self, request):
        return Response({"company": FiscalCompanySerializer(company_data()).data, "transmission_enabled": False})

    @transaction.atomic
    def patch(self, request):
        company, _ = FiscalCompany.objects.get_or_create(pk=1)
        company = FiscalCompany.objects.select_for_update().get(pk=company.pk)
        serializer = FiscalCompanySerializer(company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit_patch(request, company)
        return Response({"company": serializer.data, "transmission_enabled": False})


class FiscalCustomerView(APIView):
    permission_classes = [ACLPermission]
    acl_view = "fiscal.view"
    acl_manage = "fiscal.manage"

    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        profile = FiscalCustomerData.objects.filter(customer=customer).first() or FiscalCustomerData(customer=customer)
        return Response({"name": customer.name, "document": customer.document, "legacy_address": customer.address,
                         "data": FiscalCustomerDataSerializer(profile).data})

    @transaction.atomic
    def patch(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        profile, _ = FiscalCustomerData.objects.get_or_create(customer=customer)
        profile = FiscalCustomerData.objects.select_for_update().get(pk=profile.pk)
        serializer = FiscalCustomerDataSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit_patch(request, profile)
        return Response({"data": serializer.data})


class FiscalEquipmentView(APIView):
    permission_classes = [ACLPermission]
    acl_view = "fiscal.view"
    acl_manage = "fiscal.manage"

    def get(self, request, pk):
        equipment = get_object_or_404(Equipment, pk=pk)
        profile = FiscalEquipmentData.objects.filter(equipment=equipment).first() or FiscalEquipmentData(equipment=equipment)
        return Response({"name": equipment.name, "code": equipment.internal_code, "data": FiscalEquipmentDataSerializer(profile).data})

    @transaction.atomic
    def patch(self, request, pk):
        equipment = get_object_or_404(Equipment, pk=pk)
        profile, _ = FiscalEquipmentData.objects.get_or_create(equipment=equipment)
        profile = FiscalEquipmentData.objects.select_for_update().get(pk=profile.pk)
        serializer = FiscalEquipmentDataSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit_patch(request, profile)
        return Response({"data": serializer.data})


class FiscalRentalSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RentalQuote
        fields = ("id", "number", "customer_name", "start_date", "end_date", "status", "status_label", "total")


class FiscalRentalViewSet(ReadOnlyModelViewSet):
    permission_classes = [ACLPermission]
    acl_view = "fiscal.view"
    serializer_class = FiscalRentalSerializer
    queryset = RentalQuote.objects.select_related("customer").exclude(status__in=(RentalQuote.Status.CANCELLED, RentalQuote.Status.EXPIRED))

    @action(detail=True, methods=["get"])
    def readiness(self, request, pk=None):
        return Response(prepare_rental(self.get_object()))

    @action(detail=True, methods=["get"], url_path="export")
    def export_preparation(self, request, pk=None):
        quote = self.get_object()
        return Response(prepare_rental(quote), headers={"Content-Disposition": f'attachment; filename="pandora-preparacao-fiscal-{quote.pk}.json"'})
