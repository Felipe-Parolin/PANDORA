from datetime import date, datetime, timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import ACLPermission
from assets.models import Equipment
from assets.serializers import EquipmentSerializer
from core.models import AuditLog
from maintenance.models import ServiceOrder
from logistics.models import TransportTask
from logistics.services import ensure_transport_task, transport_completed
from .models import RentalExtension, RentalInspection, RentalQuote
from .freight import estimate_freight, lookup_cep
from .serializers import RentalInspectionSerializer, RentalQuoteSerializer
from .services import availability_reason, ensure_inspections, ensure_pre_rental_orders, refresh_equipment_status


class RentalQuoteViewSet(ModelViewSet):
    queryset = RentalQuote.objects.select_related(
        "customer", "created_by", "reserved_by", "delivered_by", "returned_by", "cancelled_by"
    ).prefetch_related("items__equipment", "inspections__equipment__category", "extensions__created_by", "transport_tasks__vehicle", "transport_tasks__driver")
    serializer_class = RentalQuoteSerializer
    permission_classes = [ACLPermission]
    acl_view = "rentals.view"
    acl_manage = "rentals.manage"

    action_permissions = {
        "reserve": "rentals.approve",
        "deliver": "rentals.dispatch",
        "extend": "rentals.extend",
        "return_rental": "rentals.return",
        "finalize_return": "rentals.return",
    }

    def get_permissions(self):
        self.acl_manage = self.action_permissions.get(getattr(self, "action", None), "rentals.manage")
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        for key, field in (("status", "status"), ("customer", "customer_id")):
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    @staticmethod
    def _require_acl(request, permission):
        if not request.user.has_acl(permission):
            raise PermissionDenied("Seu grupo não possui permissão para esta etapa da locação.")

    @staticmethod
    def _audit(request, quote, action, **data):
        AuditLog.objects.create(user=request.user, entity="RentalQuote", record_id=str(quote.pk), action=action, data=data)

    @action(detail=False, methods=["get"], url_path="lookup-address")
    def lookup_address(self, request):
        self._require_acl(request, "rentals.manage")
        address = lookup_cep(request.query_params.get("cep"))
        return Response({**address, "estimate": estimate_freight(address)})

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def reserve(self, request, pk=None):
        self._require_acl(request, "rentals.approve")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        if quote.status not in {RentalQuote.Status.DRAFT, RentalQuote.Status.SENT}:
            raise ValidationError({"status": "Somente orçamentos em rascunho ou enviados podem ser reservados."})
        if not quote.conditions.strip():
            raise ValidationError({"conditions": "Registre as condições antes de reservar."})
        equipment_ids = quote.items.values_list("equipment_id", flat=True)
        equipment = list(Equipment.objects.select_for_update().filter(pk__in=equipment_ids).order_by("pk"))
        conflicts = {item.internal_code: reason for item in equipment if (reason := availability_reason(item, quote.start_date, quote.end_date, quote))}
        if conflicts:
            raise ValidationError({"availability": conflicts})
        quote.status = RentalQuote.Status.APPROVED
        quote.reserved_by = request.user
        quote.reserved_at = timezone.now()
        quote.save(update_fields=("status", "reserved_by", "reserved_at", "updated_at"))
        ensure_inspections(quote, RentalInspection.Type.PRE_RENTAL)
        ensure_pre_rental_orders(quote, request.user)
        ensure_transport_task(quote, TransportTask.Leg.DELIVERY, request.user)
        for item in equipment:
            refresh_equipment_status(item)
        self._audit(request, quote, "RESERVED", status=quote.status, equipment=[item.internal_code for item in equipment])
        return Response(self.get_serializer(quote).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        if quote.status not in {RentalQuote.Status.DRAFT, RentalQuote.Status.SENT, RentalQuote.Status.APPROVED}:
            raise ValidationError({"status": "Uma locação entregue deve passar pelo fluxo de devolução."})
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": "Informe o motivo do cancelamento."})
        if quote.transport_tasks.filter(status=TransportTask.Status.IN_TRANSIT).exists() or quote.transport_tasks.filter(
            leg=TransportTask.Leg.DELIVERY, status=TransportTask.Status.COMPLETED
        ).exists():
            raise ValidationError({"transport": "Há equipamento em transporte ou já entregue ao destino. Conclua o fluxo de entrega e devolução."})
        quote.status = RentalQuote.Status.CANCELLED
        quote.cancelled_by = request.user
        quote.cancelled_at = timezone.now()
        quote.cancellation_reason = reason
        quote.save(update_fields=("status", "cancelled_by", "cancelled_at", "cancellation_reason", "updated_at"))
        quote.transport_tasks.filter(status=TransportTask.Status.PLANNED).update(status=TransportTask.Status.CANCELLED)
        for inspection in quote.inspections.filter(inspection_type=RentalInspection.Type.PRE_RENTAL):
            order = ServiceOrder.objects.filter(rental_inspection=inspection).first()
            if order and order.status not in {ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED} and inspection.result != RentalInspection.Result.BLOCKED:
                order.status = ServiceOrder.Status.CANCELLED
                order.save()
        for line in quote.items.select_related("equipment"):
            refresh_equipment_status(line.equipment)
        self._audit(request, quote, "CANCELLED", reason=reason)
        return Response(self.get_serializer(quote).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        self._require_acl(request, "rentals.dispatch")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        if quote.status != RentalQuote.Status.APPROVED:
            raise ValidationError({"status": "A entrega exige uma reserva aprovada."})
        inspections = list(quote.inspections.filter(inspection_type=RentalInspection.Type.PRE_RENTAL).select_related("equipment"))
        if len(inspections) != quote.items.count() or any(item.result == RentalInspection.Result.PENDING for item in inspections):
            raise ValidationError({"inspections": "Conclua a inspeção pré-locação de todos os equipamentos."})
        blocked = [item.equipment.internal_code for item in inspections if item.result == RentalInspection.Result.BLOCKED or item.critical_impediment]
        if blocked:
            raise ValidationError({"inspections": f"Equipamentos impedidos na inspeção: {', '.join(blocked)}."})
        unfinished = [item.equipment.internal_code for item in inspections if not ServiceOrder.objects.filter(
            rental_inspection=item, status=ServiceOrder.Status.COMPLETED, released=True
        ).exists()]
        if unfinished:
            raise ValidationError({"inspections": f"A inspeção na manutenção ainda não liberou: {', '.join(unfinished)}."})
        if quote.delivery_transport_required and not transport_completed(quote, TransportTask.Leg.DELIVERY):
            raise ValidationError({"transport": "Conclua a viagem de entrega antes de registrar a locação como entregue."})
        equipment_ids = quote.items.values_list("equipment_id", flat=True)
        equipment = list(Equipment.objects.select_for_update().filter(pk__in=equipment_ids).order_by("pk"))
        conflicts = {item.internal_code: reason for item in equipment if (reason := availability_reason(item, quote.start_date, quote.end_date, quote))}
        if conflicts:
            raise ValidationError({"availability": conflicts})
        delivered_at = request.data.get("delivered_at")
        try:
            delivery_time = datetime.fromisoformat(delivered_at) if delivered_at else timezone.now()
            if timezone.is_naive(delivery_time):
                delivery_time = timezone.make_aware(delivery_time)
        except (TypeError, ValueError):
            raise ValidationError({"delivered_at": "Informe uma data e hora válidas."})
        quote.status = RentalQuote.Status.ACTIVE
        quote.delivered_by = request.user
        quote.delivered_at = delivery_time
        quote.delivery_conditions = str(request.data.get("conditions", "")).strip()
        quote.save(update_fields=("status", "delivered_by", "delivered_at", "delivery_conditions", "updated_at"))
        ensure_transport_task(quote, TransportTask.Leg.RETURN, request.user)
        for inspection in inspections:
            line = quote.items.get(equipment=inspection.equipment)
            line.condition_out = f"{inspection.get_condition_display()}. {inspection.observations}".strip()
            line.save(update_fields=("condition_out",))
            refresh_equipment_status(inspection.equipment)
        self._audit(request, quote, "DELIVERED", delivered_at=delivery_time.isoformat(), conditions=quote.delivery_conditions)
        return Response(self.get_serializer(quote).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def extend(self, request, pk=None):
        self._require_acl(request, "rentals.extend")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        if quote.status not in {RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE}:
            raise ValidationError({"status": "Somente reservas e locações ativas podem ser prorrogadas."})
        try:
            new_end_date = date.fromisoformat(request.data.get("new_end_date", ""))
        except (TypeError, ValueError):
            raise ValidationError({"new_end_date": "Informe a nova data final."})
        if new_end_date <= quote.end_date:
            raise ValidationError({"new_end_date": "A nova data deve ser posterior ao término atual."})
        equipment_ids = quote.items.values_list("equipment_id", flat=True)
        equipment = list(Equipment.objects.select_for_update().filter(pk__in=equipment_ids).order_by("pk"))
        conflicts = {
            item.internal_code: reason
            for item in equipment
            if (reason := availability_reason(item, quote.end_date + timedelta(days=1), new_end_date, quote))
        }
        if conflicts:
            raise ValidationError({"availability": conflicts})
        previous = quote.end_date
        quote.end_date = new_end_date
        quote.save(update_fields=("end_date", "updated_at"))
        days = (quote.end_date - quote.start_date).days + 1
        for line in quote.items.all():
            line.quantity_days = days
            line.save(update_fields=("quantity_days", "total"))
        quote.recalculate()
        RentalExtension.objects.create(
            quote=quote,
            previous_end_date=previous,
            new_end_date=new_end_date,
            conditions=str(request.data.get("conditions", "")).strip(),
            created_by=request.user,
        )
        self._audit(request, quote, "EXTENDED", previous_end_date=previous.isoformat(), new_end_date=new_end_date.isoformat())
        return Response(self.get_serializer(quote).data)

    @transaction.atomic
    @action(detail=True, methods=["post"], url_path="return")
    def return_rental(self, request, pk=None):
        self._require_acl(request, "rentals.return")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        if quote.status != RentalQuote.Status.ACTIVE:
            raise ValidationError({"status": "Somente locações entregues podem ser devolvidas."})
        if quote.return_transport_required and not transport_completed(quote, TransportTask.Leg.RETURN):
            raise ValidationError({"transport": "Conclua a coleta de devolução antes de registrar o retorno."})
        returned_at = request.data.get("returned_at")
        try:
            return_time = datetime.fromisoformat(returned_at) if returned_at else timezone.now()
            if timezone.is_naive(return_time):
                return_time = timezone.make_aware(return_time)
        except (TypeError, ValueError):
            raise ValidationError({"returned_at": "Informe uma data e hora válidas."})
        quote.status = RentalQuote.Status.RETURNED
        quote.returned_by = request.user
        quote.returned_at = return_time
        quote.return_conditions = str(request.data.get("conditions", "")).strip()
        quote.save(update_fields=("status", "returned_by", "returned_at", "return_conditions", "updated_at"))
        ensure_inspections(quote, RentalInspection.Type.RETURN)
        for line in quote.items.select_related("equipment"):
            refresh_equipment_status(line.equipment)
        self._audit(request, quote, "RETURNED", returned_at=return_time.isoformat(), conditions=quote.return_conditions)
        return Response(self.get_serializer(quote).data)

    @transaction.atomic
    @action(detail=True, methods=["post"], url_path="finalize-return")
    def finalize_return(self, request, pk=None):
        self._require_acl(request, "rentals.return")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        if quote.status != RentalQuote.Status.RETURNED:
            raise ValidationError({"status": "A locação ainda não está aguardando inspeção final."})
        inspections = list(quote.inspections.filter(inspection_type=RentalInspection.Type.RETURN).select_related("equipment"))
        if len(inspections) != quote.items.count() or any(item.result == RentalInspection.Result.PENDING for item in inspections):
            raise ValidationError({"inspections": "Conclua a inspeção final de todos os equipamentos."})
        quote.status = RentalQuote.Status.COMPLETED
        quote.save(update_fields=("status", "updated_at"))
        routed = []
        for inspection in inspections:
            needs_service = inspection.result == RentalInspection.Result.BLOCKED or inspection.condition in {
                RentalInspection.Condition.DAMAGED, RentalInspection.Condition.CRITICAL,
            }
            if needs_service:
                ServiceOrder.objects.get_or_create(
                    rental_inspection=inspection,
                    defaults={
                        "equipment": inspection.equipment,
                        "maintenance_type": ServiceOrder.Type.POST_RENTAL,
                        "priority": "CRÍTICA" if inspection.critical_impediment else "ALTA",
                        "symptoms": inspection.observations or "Avaria identificada na inspeção de devolução.",
                        "opened_by": request.user,
                    },
                )
                routed.append(inspection.equipment.internal_code)
            refresh_equipment_status(inspection.equipment)
        self._audit(request, quote, "RETURN_COMPLETED", routed_to_maintenance=routed)
        return Response({"quote": self.get_serializer(quote).data, "routed_to_maintenance": routed})

    def destroy(self, request, *args, **kwargs):
        quote = self.get_object()
        if quote.transport_tasks.exists():
            return Response({"detail": "Há viagens vinculadas. Mantenha a locação para preservar o histórico."}, status=status.HTTP_409_CONFLICT)
        if ServiceOrder.objects.filter(rental_inspection__quote=quote).exists():
            return Response({"detail": "Há chamados de manutenção vinculados. Mantenha a locação para preservar o histórico."}, status=status.HTTP_409_CONFLICT)
        if quote.status not in {RentalQuote.Status.DRAFT, RentalQuote.Status.SENT, RentalQuote.Status.CANCELLED, RentalQuote.Status.EXPIRED}:
            return Response({"detail": "Cancele ou conclua o fluxo antes de excluir esta locação."}, status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def availability(self, request):
        try:
            start = date.fromisoformat(request.query_params["start"])
            end = date.fromisoformat(request.query_params["end"])
        except (KeyError, ValueError):
            return Response({"detail": "Informe start e end no formato AAAA-MM-DD."}, status=400)
        ignore_quote = None
        if request.query_params.get("ignore_quote"):
            try:
                ignore_quote = self.get_queryset().get(pk=request.query_params["ignore_quote"])
            except RentalQuote.DoesNotExist:
                return Response({"detail": "Orçamento informado para edição não foi encontrado."}, status=404)
        available, blocked = [], []
        for equipment in Equipment.objects.select_related("category"):
            reason = availability_reason(equipment, start, end, ignore_quote)
            (blocked if reason else available).append({"equipment": EquipmentSerializer(equipment).data, "reason": reason})
        return Response({"available": available, "blocked": blocked})


class RentalInspectionViewSet(ModelViewSet):
    queryset = RentalInspection.objects.select_related(
        "quote", "equipment", "equipment__category", "performed_by"
    ).prefetch_related("media")
    serializer_class = RentalInspectionSerializer
    permission_classes = [ACLPermission]
    acl_view = "rentals.view"
    acl_manage = ("rentals.inspect", "maintenance.manage")
    http_method_names = ("get", "patch", "head", "options")

    def get_queryset(self):
        queryset = super().get_queryset()
        for param, field in (("quote", "quote_id"), ("type", "inspection_type"), ("equipment", "equipment_id")):
            value = self.request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    def perform_update(self, serializer):
        if serializer.instance.inspection_type == RentalInspection.Type.PRE_RENTAL and not self.request.user.has_acl("maintenance.manage"):
            raise PermissionDenied("A inspeção pré-locação é registrada pela equipe de manutenção.")
        inspection = serializer.save()
        AuditLog.objects.create(
            user=self.request.user,
            entity="RentalInspection",
            record_id=str(inspection.pk),
            action="INSPECTION_UPDATED",
            data={"quote": inspection.quote_id, "type": inspection.inspection_type, "result": inspection.result},
        )
