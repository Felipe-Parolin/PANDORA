from assets.models import Equipment
from django.db.models import Q
from maintenance.models import ServiceOrder
from maintenance.services import critical_maintenance_reason
from .models import RentalInspection, RentalItem, RentalQuote


BLOCKING_RENTAL_STATUSES = (
    RentalQuote.Status.APPROVED,
    RentalQuote.Status.ACTIVE,
    RentalQuote.Status.RETURNED,
)

DEFAULT_PRE_RENTAL_CHECKLIST = (
    "Estrutura e carenagens sem avarias",
    "Proteções e dispositivos de segurança",
    "Níveis, cabos, mangueiras e conexões",
    "Teste de funcionamento e parada de emergência",
    "Limpeza e acessórios conferidos",
)

DEFAULT_RETURN_CHECKLIST = (
    "Comparar estrutura e carenagens com a saída",
    "Conferir proteções e dispositivos de segurança",
    "Verificar vazamentos, cabos e conexões",
    "Executar teste funcional e parada de emergência",
    "Conferir limpeza, combustível e acessórios",
)


def inspection_template(equipment, inspection_type):
    configured = (
        equipment.category.pre_rental_checklist
        if inspection_type == RentalInspection.Type.PRE_RENTAL
        else equipment.category.return_checklist
    )
    source = configured or (
        DEFAULT_PRE_RENTAL_CHECKLIST
        if inspection_type == RentalInspection.Type.PRE_RENTAL
        else DEFAULT_RETURN_CHECKLIST
    )
    result = []
    for index, item in enumerate(source):
        label = item.get("label", "") if isinstance(item, dict) else str(item)
        if label.strip():
            result.append({"id": str(index + 1), "label": label.strip(), "status": "PENDING", "notes": ""})
    return result


def ensure_inspections(quote, inspection_type, equipment_ids=None):
    lines = quote.items.select_related("equipment__category")
    if equipment_ids is not None:
        lines = lines.filter(equipment_id__in=equipment_ids)
    for line in lines:
        RentalInspection.objects.get_or_create(
            quote=quote,
            equipment=line.equipment,
            inspection_type=inspection_type,
            defaults={"checklist": inspection_template(line.equipment, inspection_type)},
        )


def ensure_pre_rental_orders(quote, opened_by):
    """Open one maintenance ticket per reserved equipment, without duplicating retries."""
    for inspection in quote.inspections.filter(inspection_type=RentalInspection.Type.PRE_RENTAL, equipment_id__in=quote.items.values("equipment_id")):
        ServiceOrder.objects.get_or_create(
            rental_inspection=inspection,
            defaults={
                "equipment": inspection.equipment,
                "maintenance_type": ServiceOrder.Type.PRE_RENTAL,
                "priority": "ALTA",
                "symptoms": f"Inspeção pré-locação obrigatória para a reserva {quote.number}.",
                "opened_by": opened_by,
            },
        )


def ensure_return_orders(quote, opened_by, equipment_ids=None):
    """Open one final-inspection OS per returned equipment, including clean returns."""
    current_equipment_ids = equipment_ids if equipment_ids is not None else quote.items.filter(stage__in=("RETURNED", "COMPLETED")).values_list("equipment_id", flat=True)
    for inspection in quote.inspections.filter(
        inspection_type=RentalInspection.Type.RETURN, equipment_id__in=current_equipment_ids
    ):
        needs_repair = inspection.result == RentalInspection.Result.BLOCKED or inspection.condition in {
            RentalInspection.Condition.DAMAGED, RentalInspection.Condition.CRITICAL,
        }
        completed = inspection.result in {
            RentalInspection.Result.APPROVED, RentalInspection.Result.APPROVED_WITH_NOTES,
        } and not needs_repair
        ServiceOrder.objects.get_or_create(
            rental_inspection=inspection,
            defaults={
                "equipment": inspection.equipment,
                "maintenance_type": ServiceOrder.Type.POST_RENTAL,
                "status": ServiceOrder.Status.COMPLETED if completed else ServiceOrder.Status.IN_PROGRESS if needs_repair else ServiceOrder.Status.OPEN,
                "priority": "CRÍTICA" if inspection.critical_impediment else "ALTA" if needs_repair else "NORMAL",
                "symptoms": f"Inspeção final após devolução da locação {quote.number}.",
                "diagnosis": inspection.observations if needs_repair else "",
                "opened_by": opened_by,
                "technician": inspection.performed_by if completed or needs_repair else None,
                "final_tests": "Checklist de devolução concluído." if completed else "",
                "released": completed,
            },
        )


def blocking_service_orders(equipment):
    """Return only service orders that actually immobilize the equipment.

    Scheduled preventive work does not block a rental until it starts. Also,
    pre-rental orders attached to draft/sent quotes are treated as orphaned
    preparation records and must not make the equipment unavailable forever.
    """
    pending_pre = Q(maintenance_type=ServiceOrder.Type.PRE_RENTAL, rental_inspection__quote__status__in=("APPROVED", "ACTIVE")) & ~Q(rental_inspection__result="BLOCKED")
    return ServiceOrder.objects.filter(equipment=equipment).exclude(pending_pre).exclude(
        status__in=[ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED]
    ).exclude(
        maintenance_type=ServiceOrder.Type.PREVENTIVE,
        status=ServiceOrder.Status.SCHEDULED,
    ).exclude(
        maintenance_type=ServiceOrder.Type.PRE_RENTAL,
        rental_inspection__quote__status__in=(RentalQuote.Status.DRAFT, RentalQuote.Status.SENT),
    )


def refresh_equipment_status(equipment):
    if equipment.status == Equipment.Status.INACTIVE:
        return equipment.status
    pending_pre_rental = Q(
        maintenance_type=ServiceOrder.Type.PRE_RENTAL,
        rental_inspection__quote__status__in=(RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE),
    ) & ~Q(rental_inspection__result=RentalInspection.Result.BLOCKED)
    if blocking_service_orders(equipment).exclude(pending_pre_rental).exists():
        new_status = Equipment.Status.MAINTENANCE
    elif RentalItem.objects.filter(equipment=equipment, stage="RETURNED", quote__status__in=BLOCKING_RENTAL_STATUSES).exists():
        new_status = Equipment.Status.INSPECTION
    elif RentalItem.objects.filter(equipment=equipment, stage="DELIVERED", quote__status__in=BLOCKING_RENTAL_STATUSES).exists():
        new_status = Equipment.Status.RENTED
    elif RentalItem.objects.filter(equipment=equipment, stage="PENDING", quote__status__in=("APPROVED", "ACTIVE")).exists():
        new_status = Equipment.Status.RESERVED
    else:
        new_status = Equipment.Status.AVAILABLE
    if equipment.status != new_status:
        equipment.status = new_status
        equipment.save(update_fields=("status",))
    return new_status


def availability_reason(equipment, start_date, end_date, ignore_quote=None):
    if equipment.status in {equipment.Status.MAINTENANCE, equipment.Status.INSPECTION, equipment.Status.INACTIVE}:
        return "Equipamento bloqueado pela situação operacional."
    conflicts = RentalItem.objects.filter(
        equipment=equipment,
        quote__status__in=BLOCKING_RENTAL_STATUSES,
        start_date__lte=end_date, end_date__gte=start_date,
        stage__in=("PENDING", "DELIVERED", "RETURNED"),
    )
    if ignore_quote:
        conflicts = conflicts.exclude(quote=ignore_quote)
    if conflicts.exists():
        return "Já existe uma locação aprovada no período informado."
    orders = blocking_service_orders(equipment)
    if ignore_quote:
        orders = orders.exclude(
            maintenance_type=ServiceOrder.Type.PRE_RENTAL,
            rental_inspection__quote=ignore_quote,
        )
    if orders.exists():
        return "Existe uma ordem de serviço aberta para o equipamento."
    if ServiceOrder.objects.filter(
        equipment=equipment,
        maintenance_type=ServiceOrder.Type.PREVENTIVE,
        status=ServiceOrder.Status.SCHEDULED,
        scheduled_at__date__gte=start_date,
        scheduled_at__date__lte=end_date,
    ).exists():
        return "Há manutenção preventiva agendada dentro do período informado."
    maintenance_reason = critical_maintenance_reason(equipment)
    if maintenance_reason:
        return maintenance_reason
    return None
