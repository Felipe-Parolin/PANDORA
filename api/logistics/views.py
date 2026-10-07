from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from accounts.permissions import ACLPermission
from core.models import AuditLog
from maintenance.models import ServiceOrder
from rentals.models import RentalInspection, RentalQuote
from rentals.services import availability_reason

from .models import TransportTask, Vehicle
from .serializers import TransportTaskSerializer, VehicleSerializer


class VehicleViewSet(ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    permission_classes = [ACLPermission]
    acl_view = "logistics.view"
    acl_manage = "logistics.manage"

    def destroy(self, request, *args, **kwargs):
        if self.get_object().transport_tasks.exists():
            return Response({"detail": "O veículo possui histórico de viagens e não pode ser excluído. Inative-o."}, status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)


class TransportTaskViewSet(ListModelMixin, RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    queryset = TransportTask.objects.select_related("quote__customer", "vehicle", "driver", "created_by")
    serializer_class = TransportTaskSerializer
    permission_classes = [ACLPermission]
    acl_view = "logistics.view"
    acl_manage = "logistics.manage"

    def get_queryset(self):
        queryset = super().get_queryset()
        for key, field in (("quote", "quote_id"), ("status", "status"), ("leg", "leg")):
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{field: value})
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(quote__number__icontains=search) | Q(quote__customer__name__icontains=search) | Q(vehicle__plate__icontains=search))
        return queryset

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        task = TransportTask.objects.select_for_update().get(pk=self.get_object().pk)
        if task.status != TransportTask.Status.PLANNED:
            raise ValidationError({"status": "Somente viagens planejadas podem ser iniciadas."})
        if not task.vehicle_id or not task.driver_id or not task.scheduled_at:
            raise ValidationError("Defina veículo, motorista e horário antes da saída.")
        vehicle = Vehicle.objects.select_for_update().get(pk=task.vehicle_id)
        if vehicle.status != Vehicle.Status.AVAILABLE or TransportTask.objects.filter(
            vehicle=vehicle, status=TransportTask.Status.IN_TRANSIT
        ).exclude(pk=task.pk).exists():
            raise ValidationError({"vehicle": "Veículo indisponível ou em outra viagem."})
        if not task.driver.is_active:
            raise ValidationError({"driver": "O motorista precisa estar ativo."})
        quote = RentalQuote.objects.select_for_update().get(pk=task.quote_id)
        required_status = RentalQuote.Status.APPROVED if task.leg == TransportTask.Leg.DELIVERY else RentalQuote.Status.ACTIVE
        if quote.status != required_status:
            raise ValidationError({"quote": "A locação não está na etapa desta viagem."})
        if task.leg == TransportTask.Leg.DELIVERY:
            inspections = list(quote.inspections.filter(inspection_type=RentalInspection.Type.PRE_RENTAL))
            if len(inspections) != quote.items.count() or any(
                inspection.result not in {RentalInspection.Result.APPROVED, RentalInspection.Result.APPROVED_WITH_NOTES}
                or not ServiceOrder.objects.filter(
                    rental_inspection=inspection, status=ServiceOrder.Status.COMPLETED, released=True
                ).exists()
                for inspection in inspections
            ):
                raise ValidationError({"inspections": "A manutenção deve liberar todos os equipamentos antes do transporte."})
            conflicts = {
                line.equipment.internal_code: reason
                for line in quote.items.select_related("equipment")
                if (reason := availability_reason(line.equipment, quote.start_date, quote.end_date, quote))
            }
            if conflicts:
                raise ValidationError({"availability": conflicts})
        task.status = TransportTask.Status.IN_TRANSIT
        task.departed_at = timezone.now()
        task.save(update_fields=("status", "departed_at"))
        AuditLog.objects.create(user=request.user, entity="TransportTask", record_id=str(task.pk), action="STARTED", data={"quote": quote.number, "leg": task.leg})
        return Response(self.get_serializer(task).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        task = TransportTask.objects.select_for_update().get(pk=self.get_object().pk)
        if task.status != TransportTask.Status.IN_TRANSIT:
            raise ValidationError({"status": "Somente viagens em transporte podem ser concluídas."})
        task.status = TransportTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=("status", "completed_at"))
        AuditLog.objects.create(user=request.user, entity="TransportTask", record_id=str(task.pk), action="COMPLETED", data={"quote": task.quote.number, "leg": task.leg})
        return Response(self.get_serializer(task).data)
