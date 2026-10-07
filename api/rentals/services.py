from assets.models import Equipment
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


def ensure_inspections(quote, inspection_type):
    for line in quote.items.select_related("equipment__category"):
        RentalInspection.objects.get_or_create(
            quote=quote,
            equipment=line.equipment,
            inspection_type=inspection_type,
            defaults={"checklist": inspection_template(line.equipment, inspection_type)},
        )


def refresh_equipment_status(equipment):
    if equipment.status == Equipment.Status.INACTIVE:
        return equipment.status
    if ServiceOrder.objects.filter(equipment=equipment).exclude(
        status__in=[ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED]
    ).exists():
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
    conflicts = RentalItem.objects.filter(
        equipment=equipment,
        quote__status__in=BLOCKING_RENTAL_STATUSES,
        quote__start_date__lte=end_date,
        quote__end_date__gte=start_date,
    )
    if ignore_quote:
        conflicts = conflicts.exclude(quote=ignore_quote)
    if conflicts.exists():
        return "Já existe uma locação aprovada no período informado."
    if ServiceOrder.objects.filter(equipment=equipment).exclude(status__in=[ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED]).exists():
        return "Existe uma ordem de serviço aberta para o equipamento."
    maintenance_reason = critical_maintenance_reason(equipment)
    if maintenance_reason:
        return maintenance_reason
    return None
