from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from .models import MaintenancePlan, ServiceOrder
from .patterns import ServiceOrderOpeningDirector


def plan_due_date(plan):
    if plan.next_due_date:
        return plan.next_due_date
    if plan.last_service_date and plan.interval_days:
        return plan.last_service_date + timedelta(days=plan.interval_days)
    if plan.interval_days and plan.created_at:
        return timezone.localtime(plan.created_at).date() + timedelta(days=plan.interval_days)
    return None


def generate_due_preventive_orders(today=None):
    """Open at most one preventive OS for each due plan cycle.

    A completed OS advances the plan's next due date. Running this task again
    before completion leaves the existing OS in place.
    """
    today = today or timezone.localdate()
    created_orders = []
    plan_ids = MaintenancePlan.objects.filter(
        active=True,
        maintenance_type__in=(MaintenancePlan.Type.PREVENTIVE, MaintenancePlan.Type.SCHEDULED),
        interval_days__gt=0,
    ).values_list("pk", flat=True)
    for plan_id in plan_ids.iterator():
        with transaction.atomic():
            plan = MaintenancePlan.objects.select_for_update().select_related("equipment").get(pk=plan_id)
            if not plan.active or not plan.interval_days:
                continue
            due_date = plan_due_date(plan)
            if not due_date or due_date > today:
                continue
            if plan.service_orders.exclude(
                status__in=(ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED)
            ).exists():
                continue
            if plan.service_orders.filter(plan_due_date=due_date).exists():
                continue
            priority = (
                "CRÍTICA" if plan.criticality == MaintenancePlan.Criticality.CRITICAL
                else "ALTA" if plan.criticality == MaintenancePlan.Criticality.HIGH
                else "NORMAL"
            )
            order = ServiceOrderOpeningDirector().open(
                equipment=plan.equipment,
                opened_by=None,
                symptoms=f"Manutenção preventiva agendada: {plan.name}. Revisão a cada {plan.interval_days} dias.",
                maintenance_type=ServiceOrder.Type.PREVENTIVE,
                plan=plan,
                plan_due_date=due_date,
                status=ServiceOrder.Status.SCHEDULED,
                priority=priority,
                scheduled_at=timezone.make_aware(datetime.combine(due_date, time(hour=9))),
            )
            created_orders.append(order)
            from rentals.services import refresh_equipment_status
            refresh_equipment_status(plan.equipment)
    return created_orders


def plan_due_usage_hours(plan):
    if not plan.usage_limit:
        return None
    return (plan.last_service_usage_hours or 0) + plan.usage_limit


def maintenance_alert_status(plan):
    if not plan.active:
        return "OK"

    today = timezone.localdate()
    due_date = plan_due_date(plan)
    due_usage = plan_due_usage_hours(plan)
    date_overdue = bool(due_date and due_date < today)
    usage_overdue = bool(due_usage is not None and plan.equipment.current_usage_hours >= due_usage)
    if date_overdue or usage_overdue:
        return "CRITICAL" if plan.criticality == MaintenancePlan.Criticality.CRITICAL else "OVERDUE"

    date_upcoming = bool(due_date and (due_date - today).days <= plan.advance_notice_days)
    usage_upcoming = bool(
        due_usage is not None
        and due_usage - plan.equipment.current_usage_hours <= plan.advance_notice_usage_hours
    )
    return "UPCOMING" if date_upcoming or usage_upcoming else "OK"


def critical_maintenance_reason(equipment):
    plans = equipment.maintenance_plans.filter(active=True, criticality=MaintenancePlan.Criticality.CRITICAL).select_related("equipment")
    if any(maintenance_alert_status(plan) == "CRITICAL" for plan in plans):
        return "Existe manutenção crítica vencida por data ou horas de uso."
    return None
