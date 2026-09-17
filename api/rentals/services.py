from django.utils import timezone

from maintenance.models import MaintenancePlan, ServiceOrder
from .models import RentalItem, RentalQuote


def availability_reason(equipment, start_date, end_date, ignore_quote=None):
    if equipment.status in {equipment.Status.MAINTENANCE, equipment.Status.INACTIVE}:
        return "Equipamento bloqueado pela situação operacional."
    conflicts = RentalItem.objects.filter(
        equipment=equipment,
        quote__status=RentalQuote.Status.APPROVED,
        quote__start_date__lte=end_date,
        quote__end_date__gte=start_date,
    )
    if ignore_quote:
        conflicts = conflicts.exclude(quote=ignore_quote)
    if conflicts.exists():
        return "Já existe uma locação aprovada no período informado."
    if ServiceOrder.objects.filter(equipment=equipment).exclude(status__in=[ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED]).exists():
        return "Existe uma ordem de serviço aberta para o equipamento."
    if MaintenancePlan.objects.filter(equipment=equipment, active=True, criticality=MaintenancePlan.Criticality.CRITICAL, next_due_date__lt=timezone.localdate()).exists():
        return "Existe manutenção crítica vencida."
    return None
