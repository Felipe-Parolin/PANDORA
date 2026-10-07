from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import ACLPermission
from rentals.services import refresh_equipment_status
from .models import MaintenancePlan, ServiceOrder
from .patterns import MaintenanceKitFactory
from .serializers import MaintenancePlanSerializer, ServiceOrderSerializer


class MaintenancePlanViewSet(ModelViewSet):
    queryset = MaintenancePlan.objects.select_related("equipment")
    serializer_class = MaintenancePlanSerializer
    permission_classes = [ACLPermission]
    acl_view = "maintenance.view"
    acl_manage = "maintenance.manage"

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("equipment"):
            queryset = queryset.filter(equipment_id=self.request.query_params["equipment"])
        return queryset


class ServiceOrderViewSet(ModelViewSet):
    queryset = ServiceOrder.objects.select_related("equipment", "plan", "opened_by", "technician", "rental_inspection__quote").prefetch_related("activities")
    serializer_class = ServiceOrderSerializer
    permission_classes = [ACLPermission]
    acl_view = "maintenance.view"
    acl_manage = "maintenance.manage"

    def perform_create(self, serializer):
        order = serializer.save()
        refresh_equipment_status(order.equipment)

    def perform_update(self, serializer):
        previous_equipment = serializer.instance.equipment
        order = serializer.save()
        refresh_equipment_status(previous_equipment)
        if order.equipment_id != previous_equipment.pk:
            refresh_equipment_status(order.equipment)

    def get_queryset(self):
        queryset = super().get_queryset()
        for key, field in (("status", "status"), ("type", "maintenance_type"), ("equipment", "equipment_id"), ("technician", "technician_id")):
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{field: value})
        queue = self.request.query_params.get("queue")
        if queue == "unassigned":
            queryset = queryset.filter(technician__isnull=True).exclude(
                status__in=[ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED, ServiceOrder.Status.ABANDONED]
            )
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(number__icontains=search)
                | Q(equipment__name__icontains=search)
                | Q(equipment__internal_code__icontains=search)
                | Q(symptoms__icontains=search)
            )
        return queryset

    @action(detail=False, methods=["get"], url_path="checklist-template")
    def checklist_template(self, request):
        kit = MaintenanceKitFactory.create(request.query_params.get("type", ServiceOrder.Type.CORRECTIVE))
        return Response({"checklist": kit.checklist, "route": kit.route})

    def destroy(self, request, *args, **kwargs):
        order = self.get_object()
        if order.rental_inspection_id:
            return Response({"detail": "Chamados vinculados a locações não podem ser excluídos."}, status=status.HTTP_409_CONFLICT)
        equipment = order.equipment
        response = super().destroy(request, *args, **kwargs)
        refresh_equipment_status(equipment)
        return response
