from datetime import date, datetime, timedelta
import re
from decimal import Decimal
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
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
from .documents import render_document_pdf, snapshot_for, snapshot_hash
from .models import RentalDocument, RentalExtension, RentalInspection, RentalQuote, RentalItem
from commercial.models import EquipmentPackage
from .freight import estimate_freight, estimate_period_freight, lookup_cep
from .serializers import RentalInspectionSerializer, RentalQuoteSerializer
from .operations import deliver_items, return_items, finalize_items, extend_items
from .services import availability_reason, ensure_inspections, ensure_pre_rental_orders, ensure_return_orders, refresh_equipment_status


class RentalQuoteViewSet(ModelViewSet):
    queryset = RentalQuote.objects.select_related(
        "customer", "created_by", "reserved_by", "delivered_by", "returned_by", "cancelled_by"
    ).prefetch_related("items__equipment", "inspections__equipment__category", "extensions__created_by", "transport_tasks__vehicle", "transport_tasks__driver", "transport_tasks__rental_items__equipment")
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

    @action(detail=True, methods=["get", "post"], url_path="documents")
    def documents(self, request, pk=None):
        quote = self.get_object()
        if request.method == "GET":
            history = quote.documents.select_related("created_by").order_by("kind", "-version")
            return Response([{
                "id": item.id, "kind": item.kind, "kind_label": item.get_kind_display(),
                "version": item.version, "created_at": item.created_at,
                "content_hash": item.content_hash,
                "created_by_name": item.created_by.full_name,
            } for item in history])
        kind = request.data.get("kind")
        if kind not in RentalDocument.Kind.values:
            raise ValidationError({"kind": "Selecione orçamento, entrega ou devolução."})
        with transaction.atomic():
            quote = RentalQuote.objects.select_for_update().get(pk=quote.pk)
            if kind == RentalDocument.Kind.DELIVERY and not quote.delivered_at:
                raise ValidationError({"kind": "Registre a entrega antes de gerar seu comprovante."})
            if kind == RentalDocument.Kind.RETURN and not (quote.returned_at or quote.items.filter(returned_at__isnull=False).exists()):
                raise ValidationError({"kind": "Registre a devolução antes de gerar seu comprovante."})
            snapshot = snapshot_for(quote, kind)
            digest = snapshot_hash(snapshot)
            last = quote.documents.filter(kind=kind).order_by("-version").first()
            if last and snapshot_hash(last.snapshot) != last.content_hash:
                return Response({"detail": "Integridade do documento anterior comprometida."}, status=409)
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
        filename = f"pandora-{document.snapshot['number'].lower()}-{document.kind.lower()}-v{document.version}.pdf"
        response = HttpResponse(render_document_pdf(document), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def perform_create(self, serializer):
        quote = serializer.save()
        if quote.transport_fee != quote.estimated_transport_fee:
            self._audit(
                self.request, quote, "FREIGHT_ADJUSTED",
                previous="0.00", current=str(quote.transport_fee),
                estimated=str(quote.estimated_transport_fee),
                reason=quote.transport_fee_adjustment_reason,
            )

    def perform_update(self, serializer):
        previous_fee = serializer.instance.transport_fee
        quote = serializer.save()
        if previous_fee != quote.transport_fee:
            self._audit(
                self.request, quote, "FREIGHT_ADJUSTED",
                previous=str(previous_fee), current=str(quote.transport_fee),
                estimated=str(quote.estimated_transport_fee),
                reason=quote.transport_fee_adjustment_reason,
            )

    @transaction.atomic
    @action(detail=True, methods=["post"], url_path="add-package")
    def add_package(self, request, pk=None):
        """Expands a package into real, individually validated equipment assets."""
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        if quote.status not in {RentalQuote.Status.DRAFT, RentalQuote.Status.SENT}:
            raise ValidationError({"status": "Pacotes só podem ser adicionados a orçamentos em elaboração."})
        try:
            package = EquipmentPackage.objects.prefetch_related("components__category").get(pk=request.data.get("package_id"), active=True)
        except EquipmentPackage.DoesNotExist:
            raise ValidationError({"package_id": "Pacote ativo não encontrado."})
        days = (quote.end_date - quote.start_date).days + 1
        already_selected = set(quote.items.values_list("equipment_id", flat=True))
        additions = []
        shortages = {}
        for component in package.components.all():
            candidates = Equipment.objects.select_for_update().filter(category=component.category).exclude(pk__in=already_selected).order_by("internal_code")
            selected = []
            for asset in candidates:
                reason = availability_reason(asset, quote.start_date, quote.end_date, quote)
                if not reason:
                    selected.append(asset)
                if len(selected) == component.quantity:
                    break
            if len(selected) < component.quantity:
                shortages[component.category.name] = {"requested": component.quantity, "available": len(selected), "reason": "Quantidade insuficiente sem conflito de reserva/manutenção."}
            for asset in selected:
                base_rate = component.reference_daily_rate or asset.daily_rate
                discounted_rate = (base_rate * (Decimal("100") - package.promotional_discount_percent) / Decimal("100")).quantize(Decimal("0.01"))
                additions.append(RentalItem(quote=quote, equipment=asset, daily_rate=discounted_rate, quantity_days=days, total=discounted_rate * days, start_date=quote.start_date, end_date=quote.end_date))
                already_selected.add(asset.pk)
        if shortages:
            raise ValidationError({"availability": shortages})
        if not additions:
            raise ValidationError({"package": "O pacote não possui componentes cadastrados."})
        RentalItem.objects.bulk_create(additions)
        quote.recalculate()
        self._audit(request, quote, "PACKAGE_ADDED", package_id=package.pk, package_name=package.name, equipment_ids=[x.equipment_id for x in additions])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=["get"], url_path="whatsapp-link")
    def whatsapp_link(self, request, pk=None):
        from urllib.parse import quote
        from .addresses import item_destination
        quote_obj = self.get_object()
        phone = "".join(ch for ch in (quote_obj.customer.phone or "") if ch.isdigit())
        if len(phone) < 10:
            raise ValidationError({"phone": "O cliente não possui telefone válido para abrir uma conversa."})
        if not phone.startswith("55"):
            phone = "55" + phone
        equipment_names = ", ".join(
            f"{line.equipment.internal_code} - {line.equipment.name} ({line.start_date:%d/%m/%Y} a {line.end_date:%d/%m/%Y})"
            for line in quote_obj.items.select_related("equipment").all()
        )
        transport = "Entrega/coleta no balcão"
        if quote_obj.delivery_transport_required or quote_obj.return_transport_required:
            legs = []
            for line in quote_obj.items.select_related("equipment"):
                for leg, required, label in (("DELIVERY", quote_obj.delivery_transport_required, "entrega"),("RETURN",quote_obj.return_transport_required,"coleta")):
                    if required:
                        destination = item_destination(quote_obj,line,leg)
                        schedule = timezone.localtime(destination['scheduled_at']).strftime('%d/%m/%Y às %H:%M') if destination['scheduled_at'] else str(destination['date'])+' (horário a combinar)'
                        legs.append(f"{line.equipment.internal_code}: {label} em {destination['address']}, {schedule}")
            transport = "; ".join(legs)
        message = (
            f"Olá, {quote_obj.customer.name}! Sobre a locação {quote_obj.number}: "
            f"Equipamentos: {equipment_names}. Período: {quote_obj.start_date:%d/%m/%Y} "
            f"a {quote_obj.end_date:%d/%m/%Y}. Entrega desejada: "
            f"{timezone.localtime(quote_obj.requested_delivery_at).strftime('%d/%m/%Y às %H:%M') if quote_obj.requested_delivery_at else 'a combinar'}. "
            f"Logística: {transport}. Valor total: R$ {quote_obj.total}. "
            "Por favor, confirme o recebimento desta proposta e entre em contato se precisar de ajustes."
        )
        return Response({"url": f"https://wa.me/{phone}?text={quote(message)}", "automatic_send": False})

    @action(detail=True, methods=["get"], url_path="whatsapp-extension-link")
    def whatsapp_extension_link(self, request, pk=None):
        """Create a WhatsApp deep link; no message is sent or request auto-approved."""
        from urllib.parse import quote
        quote_obj = self.get_object()
        if quote_obj.status not in {RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE}:
            raise ValidationError({"status": "Apenas reservas ou locações ativas podem solicitar prorrogação."})
        phone = "".join(ch for ch in (quote_obj.customer.phone or "") if ch.isdigit())
        if len(phone) < 10:
            raise ValidationError({"phone": "O cliente não possui telefone válido para abrir uma conversa."})
        if not phone.startswith("55"):
            phone = "55" + phone
        message = (
            f"Olá, {quote_obj.customer.name}! Gostaria de solicitar uma prorrogação da locação {quote_obj.number}. "
            f"Término atual: {quote_obj.end_date:%d/%m/%Y}. Nova data desejada: __/__/____. "
            "Por favor, analisem a disponibilidade e os valores adicionais antes de confirmar."
        )
        return Response({
            "url": f"https://wa.me/{phone}?text={quote(message)}",
            "automatic_send": False,
            "request_capture": "manual",
            "detail": "O cliente precisa enviar a mensagem no WhatsApp. Sem webhook oficial configurado, a solicitação deve ser registrada e analisada manualmente pela equipe.",
        })

    @action(detail=False, methods=["get"], url_path="lookup-address")
    def lookup_address(self, request):
        self._require_acl(request, "rentals.manage")
        raw_ids = request.query_params.get("equipment_ids", "")
        equipment_ids = [value for value in raw_ids.split(",") if value.strip().isdigit()]
        leg = request.query_params.get("leg", "DELIVERY").upper()
        if leg not in {"DELIVERY", "RETURN"}:
            raise ValidationError({"leg": "Selecione DELIVERY ou RETURN."})
        full_address = request.query_params.get("address", "").strip()
        if len(full_address) > 255:
            raise ValidationError({"address": "O endereço deve ter no máximo 255 caracteres."})
        address = lookup_cep(request.query_params.get("cep"))
        number = request.query_params.get("number", "").strip()
        if len(number) > 20:
            raise ValidationError({"number": "O número deve ter no máximo 20 caracteres."})
        allow_approximate = request.query_params.get("allow_approximate", "true").lower() == "true"
        kwargs = {"address": full_address, "leg": leg, "allow_approximate": allow_approximate}
        if number:
            kwargs['number'] = number
        periods_raw = request.query_params.get("periods")
        if periods_raw:
            import json
            from datetime import date
            try:
                periods = json.loads(periods_raw)
                if not isinstance(periods, list) or not 1 <= len(periods) <= 200:
                    raise ValueError
                ids = []
                for item in periods:
                    if not isinstance(item, dict) or isinstance(item.get("equipment_id"), bool):
                        raise ValueError
                    equipment_id = int(item["equipment_id"])
                    if str(equipment_id) != str(item["equipment_id"]):
                        raise ValueError
                    ids.append(equipment_id)
                    start, end = date.fromisoformat(item["start_date"]), date.fromisoformat(item["end_date"])
                    if end < start:
                        raise ValueError
                    if item.get('time') and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', item['time']):
                        raise ValueError
                if len(set(ids)) != len(ids) or Equipment.objects.filter(pk__in=ids).count() != len(ids):
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                raise ValidationError({"periods": "Informe equipamentos únicos com períodos válidos (máximo de 200 itens)."})
            estimate = estimate_period_freight(address, periods, **kwargs)
        else:
            estimate = estimate_freight(address, equipment_ids, **kwargs)
        return Response({**address, "estimate": estimate})

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

        # Prepare the pre-rental inspection and its maintenance OS before the
        # approval transition. Both operations are idempotent (get_or_create),
        # so a retry cannot create duplicate tickets.
        ensure_inspections(quote, RentalInspection.Type.PRE_RENTAL)
        ensure_pre_rental_orders(quote, request.user)

        # Recalculate stale equipment statuses before validating availability.
        # Orphan pre-rental OS from a draft/sent quote are ignored by the
        # availability service; real maintenance orders still block approval.
        for item in equipment:
            refresh_equipment_status(item)
        conflicts = {line.equipment.internal_code: reason for line in quote.items.select_related("equipment") if (reason := availability_reason(line.equipment, line.start_date, line.end_date, quote))}
        if conflicts:
            raise ValidationError({"availability": conflicts})
        quote.status = RentalQuote.Status.APPROVED
        quote.reserved_by = request.user
        quote.reserved_at = timezone.now()
        quote.save(update_fields=("status", "reserved_by", "reserved_at", "updated_at"))
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
        ids, when = deliver_items(quote, request.data, request.user)
        self._audit(request, quote, "DELIVERED", equipment_ids=ids, delivered_at=when.isoformat(), conditions=str(request.data.get("conditions", "")))
        return Response(self.get_serializer(quote).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def extend(self, request, pk=None):
        self._require_acl(request, "rentals.extend")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        changes = extend_items(quote, request.data, request.user)
        self._audit(request, quote, "EXTENDED", item_changes=changes)
        return Response(self.get_serializer(quote).data)

    @transaction.atomic
    @action(detail=True, methods=["post"], url_path="return")
    def return_rental(self, request, pk=None):
        self._require_acl(request, "rentals.return")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        ids, when = return_items(quote, request.data, request.user)
        self._audit(request, quote, "RETURNED", equipment_ids=ids, returned_at=when.isoformat(), conditions=str(request.data.get("conditions", "")))
        return Response(self.get_serializer(quote).data)

    @transaction.atomic
    @action(detail=True, methods=["post"], url_path="finalize-return")
    def finalize_return(self, request, pk=None):
        self._require_acl(request, "rentals.return")
        quote = RentalQuote.objects.select_for_update().get(pk=self.get_object().pk)
        ids, routed = finalize_items(quote, request.data, request.user)
        self._audit(request, quote, "RETURN_FINALIZED", equipment_ids=ids, maintenance_equipment=routed)
        return Response({**self.get_serializer(quote).data, "routed_to_maintenance": routed})

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

    @staticmethod
    def _blocked_reasons(equipment_list, start, end, ignore_quote=None):
        """Mapa equipamento -> motivo de bloqueio (ausente = disponível) para o período."""
        from maintenance.models import MaintenancePlan
        from maintenance.services import maintenance_alert_status
        from rentals.models import RentalItem
        equipment_ids = [item.pk for item in equipment_list]
        rental_conflicts = set(RentalItem.objects.filter(
            equipment_id__in=equipment_ids,
            quote__status__in=(RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED),
            start_date__lte=end, end_date__gte=start, stage__in=("PENDING", "DELIVERED", "RETURNED"),
        ).exclude(quote=ignore_quote).values_list("equipment_id", flat=True))
        orders = ServiceOrder.objects.filter(equipment_id__in=equipment_ids).exclude(
            status__in=(ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED)
        ).exclude(
            maintenance_type=ServiceOrder.Type.PREVENTIVE,
            status=ServiceOrder.Status.SCHEDULED,
        ).exclude(
            maintenance_type=ServiceOrder.Type.PRE_RENTAL,
            rental_inspection__quote__status__in=(RentalQuote.Status.DRAFT, RentalQuote.Status.SENT),
        )
        if ignore_quote:
            orders = orders.exclude(maintenance_type=ServiceOrder.Type.PRE_RENTAL, rental_inspection__quote=ignore_quote)
        from django.db.models import Q
        orders = orders.exclude(Q(maintenance_type="PRE_RENTAL", rental_inspection__quote__status__in=("APPROVED", "ACTIVE")) & ~Q(rental_inspection__result="BLOCKED"))
        open_order_ids = set(orders.values_list("equipment_id", flat=True))
        scheduled_preventive_ids = set(ServiceOrder.objects.filter(
            equipment_id__in=equipment_ids,
            maintenance_type=ServiceOrder.Type.PREVENTIVE,
            status=ServiceOrder.Status.SCHEDULED,
            scheduled_at__date__gte=start,
            scheduled_at__date__lte=end,
        ).values_list("equipment_id", flat=True))
        critical_ids = set()
        plans = MaintenancePlan.objects.filter(
            equipment_id__in=equipment_ids, active=True,
            criticality=MaintenancePlan.Criticality.CRITICAL,
        ).select_related("equipment")
        for plan in plans:
            if maintenance_alert_status(plan) == "CRITICAL":
                critical_ids.add(plan.equipment_id)
        reasons = {}
        for equipment in equipment_list:
            reason = None
            if equipment.status in {Equipment.Status.MAINTENANCE, Equipment.Status.INSPECTION, Equipment.Status.INACTIVE}:
                reason = "Equipamento bloqueado pela situação operacional."
            elif equipment.pk in rental_conflicts:
                reason = "Já existe uma locação aprovada no período informado."
            elif equipment.pk in open_order_ids:
                reason = "Existe uma ordem de serviço aberta para o equipamento."
            elif equipment.pk in scheduled_preventive_ids:
                reason = "Há manutenção preventiva agendada dentro do período informado."
            elif equipment.pk in critical_ids:
                reason = "Existe manutenção crítica vencida por data ou horas de uso."
            if reason:
                reasons[equipment.pk] = reason
        return reasons

    @action(detail=False, methods=["get"], url_path="availability-categories")
    def availability_categories(self, request):
        """Resumo por categoria: total do parque e unidades livres no período (evita listar centenas de equipamentos)."""
        try:
            start = date.fromisoformat(request.query_params["start"])
            end = date.fromisoformat(request.query_params["end"])
        except (KeyError, ValueError):
            return Response({"detail": "Informe start e end no formato AAAA-MM-DD."}, status=400)
        if end < start:
            return Response({"detail": "A data final deve ser igual ou posterior à inicial."}, status=400)
        ignore_quote = None
        if request.query_params.get("ignore_quote"):
            ignore_quote = self.get_queryset().filter(pk=request.query_params["ignore_quote"]).first()
        equipment_list = list(Equipment.objects.exclude(status=Equipment.Status.INACTIVE).select_related("category"))
        reasons = self._blocked_reasons(equipment_list, start, end, ignore_quote)
        summary = {}
        for item in equipment_list:
            row = summary.setdefault(item.category_id, {"id": item.category_id, "name": item.category.name, "parent": item.category.parent_id,
                                                        "total": 0, "available": 0, "min_daily_rate": None, "max_daily_rate": None})
            row["total"] += 1
            if item.pk not in reasons:
                row["available"] += 1
            rate = item.daily_rate
            row["min_daily_rate"] = rate if row["min_daily_rate"] is None or rate < row["min_daily_rate"] else row["min_daily_rate"]
            row["max_daily_rate"] = rate if row["max_daily_rate"] is None or rate > row["max_daily_rate"] else row["max_daily_rate"]
        from assets.models import EquipmentCategory
        for category in EquipmentCategory.objects.exclude(pk__in=summary.keys()):
            summary[category.pk] = {"id": category.pk, "name": category.name, "parent": category.parent_id, "total": 0, "available": 0,
                                    "min_daily_rate": None, "max_daily_rate": None}
        results = sorted(summary.values(), key=lambda row: row["name"].lower())
        return Response({"results": results, "count": len(results)})

    @action(detail=False, methods=["get"])
    def availability(self, request):
        try:
            start = date.fromisoformat(request.query_params["start"])
            end = date.fromisoformat(request.query_params["end"])
        except (KeyError, ValueError):
            return Response({"detail": "Informe start e end no formato AAAA-MM-DD."}, status=400)
        if end < start:
            return Response({"detail": "A data final deve ser igual ou posterior à inicial."}, status=400)
        ignore_quote = None
        if request.query_params.get("ignore_quote"):
            try:
                ignore_quote = self.get_queryset().get(pk=request.query_params["ignore_quote"])
            except RentalQuote.DoesNotExist:
                return Response({"detail": "Orçamento informado para edição não foi encontrado."}, status=404)
        from django.db.models import Q
        from maintenance.models import MaintenancePlan
        from maintenance.services import maintenance_alert_status
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = min(100, max(1, int(request.query_params.get("page_size", 50))))
        except (TypeError, ValueError):
            return Response({"detail": "Página e tamanho de página devem ser números inteiros."}, status=400)
        queryset = Equipment.objects.select_related("category").prefetch_related("media").order_by("internal_code")
        if "equipment_ids" in request.query_params:
            raw_ids = request.query_params["equipment_ids"].split(",")
            if not raw_ids or any(not value.isdigit() or int(value) < 1 for value in raw_ids):
                return Response({"detail": "Informe identificadores válidos de equipamentos."}, status=400)
            queryset = queryset.filter(pk__in={int(value) for value in raw_ids})
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(internal_code__icontains=search) |
                Q(brand__icontains=search) | Q(model__icontains=search) |
                Q(category__name__icontains=search)
            )
        if request.query_params.get("category"):
            queryset = queryset.filter(category_id=request.query_params["category"])
        if request.query_params.get("subcategory"):
            queryset = queryset.filter(category__parent_id=request.query_params["subcategory"])
        ordering = request.query_params.get("ordering", "code")
        order_fields = {"code": "internal_code", "-code": "-internal_code", "name": "name", "-name": "-name", "brand": "brand", "daily_rate": "daily_rate", "-daily_rate": "-daily_rate"}
        if ordering not in order_fields:
            raise ValidationError({"ordering": "Selecione uma ordenação válida para os equipamentos."})
        if request.query_params.get("brand"):
            queryset = queryset.filter(brand__icontains=request.query_params["brand"].strip())
        bounds = {}
        for param, lookup in (("min_daily_rate", "daily_rate__gte"), ("max_daily_rate", "daily_rate__lte")):
            if request.query_params.get(param) not in (None, ""):
                try:
                    value = Decimal(request.query_params[param])
                    if not value.is_finite() or value < 0 or value > Decimal("9999999999.99"):
                        raise ValueError
                except (ValueError, ArithmeticError):
                    raise ValidationError({param: "Informe uma diária válida entre zero e 9.999.999.999,99."})
                bounds[param] = value
                queryset = queryset.filter(**{lookup: value})
        if "min_daily_rate" in bounds and "max_daily_rate" in bounds and bounds["max_daily_rate"] < bounds["min_daily_rate"]:
            raise ValidationError({"max_daily_rate": "A diária máxima deve ser igual ou maior que a mínima."})
        queryset = queryset.order_by(order_fields[ordering], "pk")
        total = queryset.count()
        equipment_page = list(queryset[(page - 1) * page_size:page * page_size])
        reasons = self._blocked_reasons(equipment_page, start, end, ignore_quote)
        available, blocked = [], []
        for equipment in equipment_page:
            reason = reasons.get(equipment.pk)
            (blocked if reason else available).append({
                "equipment": EquipmentSerializer(equipment, context={"request": request}).data,
                "reason": reason,
            })
        return Response({
            "available": available, "blocked": blocked, "count": total,
            "page": page, "page_size": page_size,
            "next_page": page + 1 if page * page_size < total else None,
        })


class RentalInspectionViewSet(ModelViewSet):
    queryset = RentalInspection.objects.prefetch_related("quote__items").select_related(
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
