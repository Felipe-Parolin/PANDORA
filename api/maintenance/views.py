from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import ACLPermission
from rentals.services import refresh_equipment_status
from .models import MaintenancePlan, ServiceOrder
from .patterns import MaintenanceKitFactory, MaintenancePlanPrototype
from assets.models import Equipment
from .serializers import MaintenancePlanSerializer, ServiceOrderSerializer
from .services import generate_due_preventive_orders


class MaintenancePlanViewSet(ModelViewSet):
    queryset = MaintenancePlan.objects.select_related("equipment")
    serializer_class = MaintenancePlanSerializer
    permission_classes = [ACLPermission]
    acl_view = "maintenance.view"
    acl_manage = "maintenance.manage"

    @action(detail=False, methods=["post"], url_path="sync-due")
    def sync_due(self, request):
        created = generate_due_preventive_orders()
        return Response({"created": len(created), "order_ids": [order.pk for order in created]})

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, pk=None):
        """Duplica o plano para outros equipamentos (padrão Prototype), sem copiar o histórico."""
        source = self.get_object()
        ids = request.data.get("equipment_ids")
        if not isinstance(ids, list) or not ids or len(ids) > 50 or not all(isinstance(i, int) for i in ids):
            return Response({"equipment_ids": "Informe de 1 a 50 equipamentos de destino."}, status=status.HTTP_400_BAD_REQUEST)
        targets = {item.pk: item for item in Equipment.objects.filter(pk__in=ids)}
        missing = [i for i in ids if i not in targets]
        if missing:
            return Response({"equipment_ids": f"Equipamento(s) inexistente(s): {missing}"}, status=status.HTTP_400_BAD_REQUEST)
        prototype = MaintenancePlanPrototype(source)
        created, skipped = [], []
        with transaction.atomic():
            for equipment_id in dict.fromkeys(ids):
                equipment = targets[equipment_id]
                if MaintenancePlan.objects.filter(equipment=equipment, name=source.name).exists():
                    skipped.append({"equipment": equipment.pk, "reason": "Já existe um plano com este nome no equipamento."})
                    continue
                plan = prototype.clone(equipment=equipment)
                plan.save()
                created.append(plan)
        generate_due_preventive_orders()
        return Response({
            "created": MaintenancePlanSerializer(created, many=True).data, "skipped": skipped,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def perform_create(self, serializer):
        serializer.save()
        generate_due_preventive_orders()

    def perform_update(self, serializer):
        serializer.save()
        generate_due_preventive_orders()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("equipment"):
            queryset = queryset.filter(equipment_id=self.request.query_params["equipment"])
        return queryset


class ServiceOrderViewSet(ModelViewSet):
    queryset = ServiceOrder.objects.select_related("equipment", "plan", "opened_by", "technician", "rental_inspection__quote__customer").prefetch_related("activities", "rental_inspection__quote__items")
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
        if order.plan_due_date:
            return Response({"detail": "OS geradas por um plano periódico não podem ser excluídas. Ajuste o plano ou cancele o chamado."}, status=status.HTTP_409_CONFLICT)
        equipment = order.equipment
        response = super().destroy(request, *args, **kwargs)
        refresh_equipment_status(equipment)
        return response
