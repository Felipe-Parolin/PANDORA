from datetime import date, timedelta
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
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
from customers.models import Customer
from core.models import AuditLog
from maintenance.models import ServiceOrder
from logistics.models import TransportTask
from logistics.services import ensure_transport_task
from .models import RentalDocument, RentalExtension, RentalInspection, RentalQuote, UnmetRentalDemand
from .documents import render_document_pdf, snapshot_for, snapshot_hash
from .freight import estimate_freight, lookup_cep
from .fulfillment import register_delivery, register_return
from .serializers import RentalInspectionSerializer, RentalQuoteSerializer
from .services import availability_reason, ensure_inspections, ensure_pre_rental_orders, ensure_return_orders, refresh_equipment_status


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

    @action(detail=True, methods=["get", "post"], url_path="documents")
    def documents(self, request, pk=None):
        quote = self.get_object()
        if request.method == "GET":
            history = quote.documents.select_related("created_by").order_by("kind", "-version")
            return Response([{
                "id": item.id, "kind": item.kind, "kind_label": item.get_kind_display(),
                "version": item.version, "created_at": item.created_at,
                "created_by_name": item.created_by.full_name,
            } for item in history])
        kind = request.data.get("kind")
        if kind not in RentalDocument.Kind.values:
            raise ValidationError({"kind": "Selecione orçamento, entrega ou devolução."})
        if kind == RentalDocument.Kind.DELIVERY and not quote.delivered_at:
            raise ValidationError({"kind": "Registre a entrega antes de gerar seu comprovante."})
        if kind == RentalDocument.Kind.RETURN and not quote.returned_at:
            raise ValidationError({"kind": "Registre a devolução antes de gerar seu comprovante."})
        with transaction.atomic():
            quote = RentalQuote.objects.select_for_update().get(pk=quote.pk)
            snapshot = snapshot_for(quote, kind)
            digest = snapshot_hash(snapshot)
            last = quote.documents.filter(kind=kind).order_by("-version").first()
            if last and last.content_hash == digest:
                document, created = last, False
            else:
                document = RentalDocument.objects.create(
                    quote=quote, kind=kind, version=(last.version + 1 if last else 1),
                    snapshot=snapshot, content_hash=digest, created_by=request.user,
                )
                created = True
                self._audit(request, quote, "DOCUMENT_CREATED", kind=kind, version=document.version)
        return Response({"id": document.id, "kind": kind, "version": document.version, "created": created}, status=201 if created else 200)

    @action(detail=True, methods=["get"], url_path=r"documents/(?P<document_id>\d+)/pdf")
    def download_document(self, request, pk=None, document_id=None):
        quote = self.get_object()
        document = get_object_or_404(RentalDocument, quote=quote, pk=document_id)
        if snapshot_hash(document.snapshot) != document.content_hash:
            return Response({"detail": "O conteúdo deste documento não corresponde ao registro original."}, status=status.HTTP_409_CONFLICT)
        filename = f"pandora-{quote.number.lower()}-{document.kind.lower()}-v{document.version}.pdf"
        response = HttpResponse(render_document_pdf(document), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=False, methods=["post"], url_path="unmet-demand")
    def register_unmet_demand(self, request):
        self._require_acl(request, "rentals.manage")
        try:
            start = date.fromisoformat(str(request.data["start_date"]))
            end = date.fromisoformat(str(request.data["end_date"]))
        except (KeyError, ValueError):
            raise ValidationError({"dates": "Informe início e fim no formato AAAA-MM-DD."})
        if end < start:
            raise ValidationError({"end_date": "A data final deve ser igual ou posterior à inicial."})
        equipment = get_object_or_404(Equipment, pk=request.data.get("equipment"))
        customer = get_object_or_404(Customer, pk=request.data.get("customer"), is_active=True)
        reason = availability_reason(equipment, start, end)
        if not reason:
            raise ValidationError({"equipment": "O equipamento está disponível neste período; não há procura não atendida."})
        signal, created = UnmetRentalDemand.objects.get_or_create(
            equipment=equipment, customer=customer, start_date=start, end_date=end,
            defaults={"reason": reason, "created_by": request.user},
        )
        if created:
            AuditLog.objects.create(user=request.user, entity="UnmetRentalDemand", record_id=str(signal.pk), action="CREATED", data={"equipment": equipment.internal_code, "reason": reason})
        return Response({"id": signal.id, "created": created, "reason": signal.reason}, status=201 if created else 200)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def reserve(self, request, pk=None):
        self._require_acl(request, "rentals.approve")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        if quote.status not in {RentalQuote.Status.DRAFT, RentalQuote.Status.SENT}:
            raise ValidationError({"status": "Somente orçamentos em rascunho ou enviados podem ser reservados."})
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
        quote = register_delivery(self.get_object().pk, request.user, request.data.get("delivered_at"), request.data.get("conditions", ""))
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
        quote = register_return(self.get_object().pk, request.user, request.data.get("returned_at"), request.data.get("conditions", ""))
        return Response(self.get_serializer(quote).data)

    @transaction.atomic
    @action(detail=True, methods=["post"], url_path="finalize-return")
    def finalize_return(self, request, pk=None):
        self._require_acl(request, "rentals.return")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        if quote.status != RentalQuote.Status.RETURNED:
            raise ValidationError({"status": "A locação ainda não está aguardando inspeção final."})
        current_equipment_ids = quote.items.values_list("equipment_id", flat=True)
        inspections = list(quote.inspections.filter(
            inspection_type=RentalInspection.Type.RETURN, equipment_id__in=current_equipment_ids
        ).select_related("equipment"))
        if len(inspections) != quote.items.count() or any(item.result == RentalInspection.Result.PENDING for item in inspections):
            raise ValidationError({"inspections": "Conclua a inspeção final de todos os equipamentos."})
        ensure_return_orders(quote, request.user)
        quote.status = RentalQuote.Status.COMPLETED
        quote.save(update_fields=("status", "updated_at"))
        routed = []
        for inspection in inspections:
            needs_service = inspection.result == RentalInspection.Result.BLOCKED or inspection.condition in {
                RentalInspection.Condition.DAMAGED, RentalInspection.Condition.CRITICAL,
            }
            if needs_service:
                routed.append(inspection.equipment.internal_code)
            refresh_equipment_status(inspection.equipment)
        self._audit(request, quote, "RETURN_COMPLETED", routed_to_maintenance=routed)
        return Response({"quote": self.get_serializer(quote).data, "routed_to_maintenance": routed})

    def destroy(self, request, *args, **kwargs):
        quote = self.get_object()
        if quote.documents.exists():
            return Response({"detail": "Há documentos versionados. Mantenha a locação para preservar o histórico."}, status=status.HTTP_409_CONFLICT)
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
        if serializer.instance.inspection_type == RentalInspection.Type.PRE_RENTAL:
            if not self.request.user.has_acl("maintenance.manage"):
                raise PermissionDenied("A inspeção pré-locação é registrada pela equipe de manutenção.")
        elif not (
            self.request.user.has_acl("maintenance.manage")
            or self.request.user.has_acl("maintenance.view") and self.request.user.has_acl("rentals.inspect")
        ):
            raise PermissionDenied("A inspeção final exige acesso à Manutenção e permissão para inspecionar devoluções.")
        inspection = serializer.save()
        AuditLog.objects.create(
            user=self.request.user,
            entity="RentalInspection",
            record_id=str(inspection.pk),
            action="INSPECTION_UPDATED",
            data={"quote": inspection.quote_id, "type": inspection.inspection_type, "result": inspection.result},
        )
