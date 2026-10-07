from datetime import timedelta

from django.utils import timezone

from .models import MaintenancePlan


def plan_due_date(plan):
    if plan.next_due_date:
        return plan.next_due_date
    if plan.last_service_date and plan.interval_days:
        return plan.last_service_date + timedelta(days=plan.interval_days)
    return None


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
