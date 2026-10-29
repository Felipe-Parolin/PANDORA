"""Shared, permission-checked movements for counter service and transport."""
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from assets.models import Equipment
from core.models import AuditLog
from logistics.models import TransportTask
from logistics.services import ensure_transport_task, transport_completed
from maintenance.models import ServiceOrder
from .models import RentalInspection, RentalQuote
from .services import availability_reason, ensure_inspections, ensure_return_orders, refresh_equipment_status


def operation_time(value, field):
    try:
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(value) if value else timezone.now()
        return timezone.make_aware(moment) if timezone.is_naive(moment) else moment
    except (TypeError, ValueError):
        raise ValidationError({field: "Informe uma data e hora válidas."})


@transaction.atomic
def register_delivery(quote_id, actor, delivered_at=None, conditions=""):
    if not actor.has_acl("rentals.dispatch"):
        raise PermissionDenied("Seu grupo não pode confirmar a entrega da locação.")
    quote = RentalQuote.objects.select_for_update().get(pk=quote_id)
    if quote.status != RentalQuote.Status.APPROVED:
        raise ValidationError({"status": "A entrega exige uma reserva aprovada."})
    inspections = list(quote.inspections.filter(
        inspection_type=RentalInspection.Type.PRE_RENTAL,
        equipment_id__in=quote.items.values_list("equipment_id", flat=True),
    ).select_related("equipment"))
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
    equipment = list(Equipment.objects.select_for_update().filter(
        pk__in=quote.items.values_list("equipment_id", flat=True)
    ).order_by("pk"))
    conflicts = {item.internal_code: reason for item in equipment if (reason := availability_reason(item, quote.start_date, quote.end_date, quote))}
    if conflicts:
        raise ValidationError({"availability": conflicts})
    quote.status = RentalQuote.Status.ACTIVE
    quote.delivered_by = actor
    quote.delivered_at = operation_time(delivered_at, "delivered_at")
    quote.delivery_conditions = str(conditions).strip()
    quote.save(update_fields=("status", "delivered_by", "delivered_at", "delivery_conditions", "updated_at"))
    ensure_transport_task(quote, TransportTask.Leg.RETURN, actor)
    for inspection in inspections:
        line = quote.items.get(equipment=inspection.equipment)
        line.condition_out = f"{inspection.get_condition_display()}. {inspection.observations}".strip()
        line.save(update_fields=("condition_out",))
        refresh_equipment_status(inspection.equipment)
    AuditLog.objects.create(user=actor, entity="RentalQuote", record_id=str(quote.pk), action="DELIVERED", data={
        "delivered_at": quote.delivered_at.isoformat(), "conditions": quote.delivery_conditions,
    })
    return quote


@transaction.atomic
def register_return(quote_id, actor, returned_at=None, conditions=""):
    if not actor.has_acl("rentals.return"):
        raise PermissionDenied("Seu grupo não pode confirmar a devolução da locação.")
    quote = RentalQuote.objects.select_for_update().get(pk=quote_id)
    if quote.status != RentalQuote.Status.ACTIVE:
        raise ValidationError({"status": "Somente locações entregues podem ser devolvidas."})
    if quote.return_transport_required and not transport_completed(quote, TransportTask.Leg.RETURN):
        raise ValidationError({"transport": "Conclua a coleta de devolução antes de registrar o retorno."})
    quote.status = RentalQuote.Status.RETURNED
    quote.returned_by = actor
    quote.returned_at = operation_time(returned_at, "returned_at")
    quote.return_conditions = str(conditions).strip()
    quote.save(update_fields=("status", "returned_by", "returned_at", "return_conditions", "updated_at"))
    ensure_inspections(quote, RentalInspection.Type.RETURN)
    ensure_return_orders(quote, actor)
    for line in quote.items.select_related("equipment"):
        refresh_equipment_status(line.equipment)
    AuditLog.objects.create(user=actor, entity="RentalQuote", record_id=str(quote.pk), action="RETURNED", data={
        "returned_at": quote.returned_at.isoformat(), "conditions": quote.return_conditions,
    })
    return quote
