"""Operações atômicas por equipamento; a view mantém o bloqueio da locação."""
from datetime import date, datetime
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from maintenance.models import ServiceOrder
from logistics.models import TransportTask
from logistics.services import ensure_transport_task, transport_completed
from assets.models import Equipment
from .models import RentalItem, RentalInspection, RentalExtension, RentalQuote
from .services import availability_reason, ensure_inspections, ensure_return_orders, refresh_equipment_status


def selected_lines(quote, data, stages):
    queryset = quote.items.select_related("equipment")
    ids = data.get("equipment_ids")
    if ids is not None:
        if not isinstance(ids, list) or not ids or any(isinstance(item, bool) or not str(item).isdigit() for item in ids):
            raise ValidationError({"equipment_ids": "Selecione os equipamentos desta operação."})
        ids = [int(item) for item in ids]
        if len(ids) != len(set(ids)):
            raise ValidationError({"equipment_ids": "Não repita equipamentos."})
        lines = list(queryset.filter(equipment_id__in=ids))
        if len(lines) != len(ids) or any(line.stage not in stages for line in lines):
            raise ValidationError({"equipment_ids": "Selecione apenas itens desta locação na etapa correta."})
    else:
        lines = list(queryset.filter(stage__in=stages))
    if not lines:
        raise ValidationError({"equipment_ids": "Não há equipamentos disponíveis para esta operação."})
    # Mesma ordem em todas as operações, evitando concorrência sobre o mesmo patrimônio.
    list(Equipment.objects.select_for_update().filter(pk__in=[line.equipment_id for line in lines]).order_by("pk"))
    return lines


def operation_time(data, field):
    try:
        value = datetime.fromisoformat(data[field]) if data.get(field) else timezone.now()
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    except (ValueError, TypeError):
        raise ValidationError({field: "Informe uma data e hora válidas."})


def sync_quote_stage(quote):
    lines = list(quote.items.all())
    if lines and all(line.stage == RentalItem.Stage.COMPLETED for line in lines):
        quote.status = RentalQuote.Status.COMPLETED
    elif lines and all(line.stage in {RentalItem.Stage.RETURNED, RentalItem.Stage.COMPLETED} for line in lines):
        quote.status = RentalQuote.Status.RETURNED
    elif any(line.stage != RentalItem.Stage.PENDING for line in lines):
        quote.status = RentalQuote.Status.ACTIVE
    deliveries = [line.delivered_at for line in lines if line.delivered_at]
    if deliveries:
        quote.delivered_at = min(deliveries)
    if lines and all(line.stage in {RentalItem.Stage.RETURNED, RentalItem.Stage.COMPLETED} for line in lines):
        returns = [line.returned_at for line in lines if line.returned_at]
        if returns:
            quote.returned_at = max(returns)
    quote.save(update_fields=("status", "delivered_at", "returned_at", "delivered_by", "returned_by", "delivery_conditions", "return_conditions", "updated_at"))


def deliver_items(quote, data, actor):
    if quote.status not in {RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE}:
        raise ValidationError({"status": "A entrega exige uma reserva aprovada ou parcialmente entregue."})
    lines = selected_lines(quote, data, {RentalItem.Stage.PENDING})
    ids = [line.equipment_id for line in lines]
    inspections = list(quote.inspections.filter(inspection_type="PRE_RENTAL", equipment_id__in=ids))
    if len(inspections) != len(lines) or any(item.result not in {"APPROVED", "APPROVED_WITH_NOTES"} or item.critical_impediment for item in inspections):
        raise ValidationError({"inspections": "Conclua e aprove a inspeção dos equipamentos selecionados."})
    if any(not ServiceOrder.objects.filter(rental_inspection=item, status="COMPLETED", released=True).exists() for item in inspections):
        raise ValidationError({"inspections": "A manutenção ainda não liberou todos os itens selecionados."})
    if quote.delivery_transport_required and not transport_completed(quote, "DELIVERY", lines):
        raise ValidationError({"transport": "Conclua o transporte dos equipamentos selecionados antes de registrar a entrega."})
    conflicts = {}
    for line in lines:
        refresh_equipment_status(line.equipment)
        reason = availability_reason(line.equipment, line.start_date, line.end_date, quote)
        if RentalItem.objects.filter(equipment=line.equipment, stage="DELIVERED", quote__status="ACTIVE").exclude(quote=quote).exists():
            reason = "O equipamento ainda não retornou de outra locação."
        if reason:
            conflicts[line.equipment.internal_code] = reason
    if conflicts:
        raise ValidationError({"availability": conflicts})
    when = operation_time(data, "delivered_at")
    conditions = str(data.get("conditions", "")).strip()
    for line in lines:
        inspection = next(item for item in inspections if item.equipment_id == line.equipment_id)
        line.stage, line.delivered_at, line.delivered_by = "DELIVERED", when, actor
        line.delivery_conditions = conditions
        line.condition_out = f"{inspection.get_condition_display()}. {inspection.observations}".strip()
        line.save(update_fields=("stage", "delivered_at", "delivered_by", "delivery_conditions", "condition_out"))
    if not quote.delivered_by_id:
        quote.delivered_by = actor
    quote.delivery_conditions = conditions
    sync_quote_stage(quote)
    from commercial.receivables import post_quote_receivable
    post_quote_receivable(quote, actor)
    ensure_transport_task(quote, TransportTask.Leg.RETURN, actor, items=lines)
    for line in lines:
        refresh_equipment_status(line.equipment)
    return ids, when


def return_items(quote, data, actor):
    if quote.status != RentalQuote.Status.ACTIVE:
        raise ValidationError({"status": "Somente equipamentos entregues podem ser devolvidos."})
    lines = selected_lines(quote, data, {RentalItem.Stage.DELIVERED})
    if quote.return_transport_required and not transport_completed(quote, "RETURN", lines):
        raise ValidationError({"transport": "Conclua a coleta dos equipamentos selecionados antes de registrar o retorno."})
    when = operation_time(data, "returned_at")
    if any(line.delivered_at and when < line.delivered_at for line in lines):
        raise ValidationError({"returned_at": "A devolução não pode ocorrer antes da entrega do equipamento."})
    for line in lines:
        line.stage, line.returned_at, line.returned_by = "RETURNED", when, actor
        line.return_conditions = str(data.get("conditions", "")).strip()
        line.save(update_fields=("stage", "returned_at", "returned_by", "return_conditions"))
    quote.returned_by = actor
    quote.return_conditions = str(data.get("conditions", "")).strip()
    sync_quote_stage(quote)
    ids = [line.equipment_id for line in lines]
    ensure_inspections(quote, "RETURN", equipment_ids=ids)
    ensure_return_orders(quote, actor, equipment_ids=ids)
    for line in lines:
        refresh_equipment_status(line.equipment)
    return ids, when


def finalize_items(quote, data, actor):
    if quote.status not in {RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED}:
        raise ValidationError({"status": "A locação não possui devoluções aguardando conclusão."})
    lines = selected_lines(quote, data, {RentalItem.Stage.RETURNED})
    ids = [line.equipment_id for line in lines]
    inspections = list(quote.inspections.filter(inspection_type="RETURN", equipment_id__in=ids))
    if len(inspections) != len(lines) or any(item.result == "PENDING" for item in inspections):
        raise ValidationError({"inspections": "Conclua a inspeção final dos equipamentos selecionados."})
    ensure_return_orders(quote, actor, equipment_ids=ids)
    for line in lines:
        line.stage, line.finalized_at = "COMPLETED", timezone.now()
        line.save(update_fields=("stage", "finalized_at"))
        refresh_equipment_status(line.equipment)
    sync_quote_stage(quote)
    return ids, [item.equipment.internal_code for item in inspections if item.result == "BLOCKED" or item.condition in {"DAMAGED", "CRITICAL"}]


def extend_items(quote, data, actor):
    if quote.status not in {RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE}:
        raise ValidationError({"status": "Somente itens reservados ou com o cliente podem ser prorrogados."})
    lines = selected_lines(quote, data, {RentalItem.Stage.PENDING, RentalItem.Stage.DELIVERED})
    try:
        new_end = date.fromisoformat(data.get("new_end_date", ""))
    except (ValueError, TypeError):
        raise ValidationError({"new_end_date": "Informe a nova data final."})
    if any(new_end <= line.end_date for line in lines):
        raise ValidationError({"new_end_date": "A nova data deve ser posterior ao término de cada item selecionado."})
    from django.db.models import Q
    tasks = quote.transport_tasks.filter(leg="RETURN").filter(Q(items_scoped=False) | Q(rental_items__in=lines)).distinct()
    if tasks.filter(status__in=("IN_TRANSIT", "COMPLETED")).exists():
        raise ValidationError({"transport": "Há coleta em andamento ou concluída para um item selecionado."})
    from datetime import timedelta
    conflicts = {line.equipment.internal_code: reason for line in lines if (reason := availability_reason(line.equipment, line.end_date+timedelta(days=1), new_end, quote))}
    if conflicts:
        raise ValidationError({"availability": conflicts})
    previous = quote.end_date
    changes = [{"equipment": line.equipment_id, "code": line.equipment.internal_code, "previous_end_date": str(line.end_date), "new_end_date": str(new_end)} for line in lines]
    for line in lines:
        line.end_date = new_end; line.save(update_fields=("end_date",))
    for task in tasks.filter(status="PLANNED"):
        if not task.items_scoped:
            task.rental_items.set(quote.items.all())
            task.items_scoped = True
            task.save(update_fields=("items_scoped",))
        task.rental_items.remove(*lines)
        if not task.rental_items.exists():
            task.status = "CANCELLED"; task.save(update_fields=("status",))
    all_lines = list(quote.items.all())
    quote.start_date, quote.end_date = min(line.start_date for line in all_lines), max(line.end_date for line in all_lines)
    quote.save(update_fields=("start_date", "end_date", "updated_at")); quote.recalculate()
    ensure_transport_task(quote, "RETURN", actor, items=[line for line in lines if line.stage == "DELIVERED"])
    RentalExtension.objects.create(quote=quote, previous_end_date=previous, new_end_date=quote.end_date, item_changes=changes, conditions=str(data.get("conditions", "")).strip(), created_by=actor)
    from commercial.receivables import post_quote_receivable
    post_quote_receivable(quote, actor)
    for line in lines:
        refresh_equipment_status(line.equipment)
    return changes
