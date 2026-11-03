"""Relatório operacional (RI5 / RF36): disponibilidade, locações, atrasos e manutenções."""
from collections import Counter
from datetime import timedelta

from django.db.models import Avg, ExpressionWrapper, F, DurationField
from django.utils import timezone

from assets.models import Equipment
from maintenance.models import MaintenancePlan, ServiceOrder
from maintenance.services import maintenance_alert_status, plan_due_date
from rentals.models import RentalQuote

from .risk import RiskAnalyzer

OPEN_STATUSES = (ServiceOrder.Status.OPEN, ServiceOrder.Status.SCHEDULED, ServiceOrder.Status.IN_PROGRESS, ServiceOrder.Status.WAITING_PARTS, ServiceOrder.Status.ABANDONED)
STALE_ORDER_DAYS = 7


def build_operational_report(start, end, analyzer: RiskAnalyzer | None = None) -> dict:
    today = timezone.localdate()
    now = timezone.now()
    analyzer = analyzer or RiskAnalyzer()

    equipment = list(Equipment.objects.all())
    by_status = Counter(item.status for item in equipment)
    active_fleet = sum(count for status, count in by_status.items() if status != Equipment.Status.INACTIVE) or 1
    blocked = [
        {"id": e.pk, "code": e.internal_code, "name": e.name, "status": e.status, "status_label": e.get_status_display()}
        for e in equipment if e.status in (Equipment.Status.MAINTENANCE, Equipment.Status.INSPECTION)
    ]

    counted = (RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED, RentalQuote.Status.COMPLETED)
    quotes = RentalQuote.objects.filter(status__in=counted, items__start_date__lte=end, items__end_date__gte=start).distinct().prefetch_related("items__equipment")
    late_returns, late_deliveries = [], []
    for quote in RentalQuote.objects.filter(status__in=(RentalQuote.Status.ACTIVE, RentalQuote.Status.APPROVED)).prefetch_related("items__equipment"):
        overdue_returns = [item for item in quote.items.all() if item.stage == "DELIVERED" and item.end_date < today]
        overdue_deliveries = [item for item in quote.items.all() if item.stage == "PENDING" and item.start_date < today]
        if overdue_returns:
            due = min(item.end_date for item in overdue_returns)
            late_returns.append({"number": quote.number, "end_date": due.isoformat(), "days_late": (today-due).days, "equipment": [item.equipment.name for item in overdue_returns]})
        if overdue_deliveries:
            due = min(item.start_date for item in overdue_deliveries)
            late_deliveries.append({"number": quote.number, "start_date": due.isoformat(), "days_late": (today-due).days, "equipment": [item.equipment.name for item in overdue_deliveries]})

    orders = ServiceOrder.objects.select_related("equipment")
    late_orders = []
    for order in orders.filter(status__in=OPEN_STATUSES):
        age = (now - order.opened_at).days
        overdue_schedule = order.status == ServiceOrder.Status.SCHEDULED and order.scheduled_at and order.scheduled_at < now
        if age >= STALE_ORDER_DAYS or overdue_schedule:
            late_orders.append({
                "id": order.pk, "number": order.number, "equipment": order.equipment.name, "status": order.status,
                "status_label": order.get_status_display(), "days_open": age,
                "reason": "Agendamento vencido" if overdue_schedule else f"Aberta há {age} dias",
            })
    late_orders.sort(key=lambda item: -item["days_open"])
    in_window = orders.filter(opened_at__date__lte=end, opened_at__date__gte=start)
    resolution = orders.filter(status=ServiceOrder.Status.COMPLETED, closed_at__isnull=False, closed_at__date__gte=start, closed_at__date__lte=end).aggregate(
        avg=Avg(ExpressionWrapper(F("closed_at") - F("opened_at"), output_field=DurationField()))
    )["avg"]

    plans = MaintenancePlan.objects.filter(active=True).select_related("equipment")
    plan_status = Counter()
    overdue_plans = []
    for plan in plans:
        state = maintenance_alert_status(plan)
        plan_status[state] += 1
        if state in {"OVERDUE", "CRITICAL"}:
            due = plan_due_date(plan)
            overdue_plans.append({"id": plan.pk, "plan": plan.name, "equipment": plan.equipment.name, "state": state, "due_date": due.isoformat() if due else None})

    return {
        "generated_at": now.isoformat(),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "availability": {
            "total": len(equipment), "by_status": dict(by_status),
            "available_rate": round(by_status.get(Equipment.Status.AVAILABLE, 0) / active_fleet * 100, 1), "blocked": blocked,
        },
        "rentals": {
            "in_period": quotes.count(), "by_status": dict(Counter(q.status for q in quotes)),
            "late_returns": late_returns, "late_deliveries": late_deliveries,
        },
        "maintenance": {
            "opened_in_period": in_window.count(), "open_now": orders.filter(status__in=OPEN_STATUSES).count(),
            "by_type": dict(Counter(in_window.values_list("maintenance_type", flat=True))),
            "late_orders": late_orders[:15], "plans_by_state": dict(plan_status), "overdue_plans": overdue_plans,
            "avg_resolution_days": round(resolution.total_seconds() / 86400, 1) if resolution else None,
        },
        "recurrence": [
            {"equipment_id": a.equipment_id, "name": a.equipment_name, "code": a.internal_code, "score": a.score, "level": a.level, "level_label": a.level_label}
            for a in analyzer.ranking(limit=5)
        ],
    }


def default_period(days=30):
    end = timezone.localdate()
    return end - timedelta(days=days), end
