from datetime import timedelta

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

def ensure_inspections(quote, inspection_type):
    """Create one decision record per rented item; legacy checklists remain archived."""
    for line in quote.items.select_related("equipment"):
        RentalInspection.objects.get_or_create(
            quote=quote,
            equipment=line.equipment,
            inspection_type=inspection_type,
        )


def ensure_pre_rental_orders(quote, opened_by):
    """Open one maintenance ticket per reserved equipment, without duplicating retries."""
    for inspection in quote.inspections.filter(inspection_type=RentalInspection.Type.PRE_RENTAL):
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


def ensure_return_orders(quote, opened_by):
    """Open one final-inspection OS per returned equipment, including clean returns."""
    current_equipment_ids = quote.items.values_list("equipment_id", flat=True)
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
                "final_tests": "Condição operante confirmada na devolução." if completed else "",
                "released": completed,
            },
        )


def blocking_service_orders(equipment):
    return ServiceOrder.objects.filter(equipment=equipment).exclude(
        status__in=[ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED]
    )


def refresh_equipment_status(equipment):
    if equipment.status == Equipment.Status.INACTIVE:
        return equipment.status
    pending_pre_rental = Q(
        maintenance_type=ServiceOrder.Type.PRE_RENTAL,
        rental_inspection__quote__status=RentalQuote.Status.APPROVED,
    ) & ~Q(rental_inspection__result=RentalInspection.Result.BLOCKED)
    if blocking_service_orders(equipment).exclude(pending_pre_rental).exists():
        new_status = Equipment.Status.MAINTENANCE
    elif RentalItem.objects.filter(equipment=equipment, quote__status=RentalQuote.Status.RETURNED).exists():
        new_status = Equipment.Status.INSPECTION
    elif RentalItem.objects.filter(equipment=equipment, quote__status=RentalQuote.Status.ACTIVE).exists():
        new_status = Equipment.Status.RENTED
    elif RentalItem.objects.filter(equipment=equipment, quote__status=RentalQuote.Status.APPROVED).exists():
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
    turnaround = equipment.turnaround_days or 0
    conflicts = RentalItem.objects.filter(
        equipment=equipment,
        quote__status__in=BLOCKING_RENTAL_STATUSES,
        quote__start_date__lte=end_date + timedelta(days=turnaround),
        quote__end_date__gte=start_date - timedelta(days=turnaround),
    )
    if ignore_quote:
        conflicts = conflicts.exclude(quote=ignore_quote)
    if conflicts.exists():
        if not conflicts.filter(quote__start_date__lte=end_date, quote__end_date__gte=start_date).exists():
            return f"Intervalo operacional de {turnaround} dia(s) para limpeza, transporte ou preparo entre locações."
        return "Já existe uma locação aprovada no período informado."
    orders = blocking_service_orders(equipment)
    if ignore_quote:
        orders = orders.exclude(
            maintenance_type=ServiceOrder.Type.PRE_RENTAL,
            rental_inspection__quote=ignore_quote,
        )
    if orders.exists():
        return "Existe uma ordem de serviço aberta para o equipamento."
    maintenance_reason = critical_maintenance_reason(equipment)
    if maintenance_reason:
        return maintenance_reason
    return None
