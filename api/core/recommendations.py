"""Explainable purchase signals, never an automatic purchase decision."""

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from assets.models import Equipment
from maintenance.models import ServiceOrder
from rentals.models import RentalItem, RentalQuote, UnmetRentalDemand


OCCUPYING_STATUSES = {
    RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE,
    RentalQuote.Status.RETURNED, RentalQuote.Status.COMPLETED,
}


def suggest_equipment_purchase(days=180):
    today = timezone.localdate()
    first_day = today - timedelta(days=days - 1)
    since = timezone.now() - timedelta(days=days)
    demand = {
        row["equipment_id"]: row
        for row in RentalItem.objects.filter(quote__created_at__gte=since)
        .exclude(quote__status__in=(RentalQuote.Status.CANCELLED, RentalQuote.Status.EXPIRED))
        .values("equipment_id")
        .annotate(
            requests=Count("quote_id", distinct=True),
            requested_days=Sum("quantity_days"),
            open_interest=Count("quote_id", filter=Q(quote__status__in=(
                RentalQuote.Status.DRAFT, RentalQuote.Status.SENT,
                RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE,
            )), distinct=True),
        )
    }
    unmet = Counter(dict(UnmetRentalDemand.objects.filter(created_at__gte=since).values("equipment_id").annotate(total=Count("id")).values_list("equipment_id", "total")))
    costs = {
        row["equipment_id"]: (row["labor"] or Decimal("0")) + (row["parts"] or Decimal("0"))
        for row in ServiceOrder.objects.filter(opened_at__gte=since).exclude(status=ServiceOrder.Status.CANCELLED)
        .values("equipment_id").annotate(labor=Sum("labor_cost"), parts=Sum("parts_cost"))
    }
    occupied = defaultdict(set)
    for item in RentalItem.objects.filter(
        quote__status__in=OCCUPYING_STATUSES,
        quote__start_date__lte=today,
        quote__end_date__gte=first_day,
    ).select_related("quote"):
        start = max(item.quote.start_date, first_day)
        end = min(item.quote.end_date, today)
        occupied[item.equipment_id].update(range(start.toordinal(), end.toordinal() + 1))
    fleet = list(Equipment.objects.select_related("category"))
    category_size = Counter(item.category_id for item in fleet if item.status != Equipment.Status.INACTIVE)
    category_available = Counter(item.category_id for item in fleet if item.status == Equipment.Status.AVAILABLE)
    candidates = []
    for item in fleet:
        if item.status == Equipment.Status.INACTIVE:
            continue
        signal = demand.get(item.id, {})
        requests = signal.get("requests", 0)
        lost = unmet[item.id]
        if not requests and not lost:
            continue
        utilization = round(len(occupied[item.id]) / days * 100, 1)
        maintenance_cost = costs.get(item.id, Decimal("0"))
        acquisition = item.acquisition_cost
        replacement_pressure = bool(acquisition and maintenance_cost >= acquisition * Decimal("0.35") and utilization < 30)
        score = lost * 6 + requests * 2 + utilization / 10 + (3 if category_available[item.category_id] == 0 else 0) + (3 if replacement_pressure else 0)
        candidates.append((score, requests + lost, item, signal, lost, utilization, maintenance_cost, replacement_pressure))
    if not candidates:
        return {"status": "INSUFFICIENT_DATA", "source": "rental_history", "message": "Registre orçamentos ou procura não atendida antes de avaliar uma nova compra.", "period_days": days}
    _, _, item, signal, lost, utilization, maintenance_cost, replacement_pressure = max(candidates, key=lambda row: (row[0], row[1], -row[2].id))
    requests = signal.get("requests", 0)
    requested_days = signal.get("requested_days") or 0
    available = category_available[item.category_id]
    acquired = str(item.acquisition_cost) if item.acquisition_cost is not None else None
    confidence = "HIGH" if requests + lost >= 8 and acquired else "MEDIUM" if requests + lost >= 3 and acquired else "LOW"
    suggestion = f"Avaliar a substituição de {item.name}." if replacement_pressure else f"Avaliar a compra de mais uma unidade de {item.name}."
    reason = f"{requests} solicitação(ões), {lost} procura(s) não atendida(s), ocupação de {utilization}% e custo de manutenção de R$ {maintenance_cost:.2f} nos últimos {days} dias."
    return {
        "status": "REVIEW",
        "source": "rental_history",
        "equipment_id": item.id,
        "equipment_name": item.name,
        "category_name": item.category.name,
        "recommendation_type": "REPLACEMENT" if replacement_pressure else "EXPANSION",
        "suggestion": suggestion,
        "reason": reason,
        "evidence": {
            "requests": requests,
            "requested_days": requested_days,
            "open_interest": signal.get("open_interest", 0),
            "unmet_demand": lost,
            "utilization_percent": utilization,
            "maintenance_cost": str(maintenance_cost),
            "acquisition_cost": acquired,
            "category_fleet": category_size[item.category_id],
            "category_available": available,
        },
        "confidence": confidence,
        "period_days": days,
    }
