"""Roteiro do dia: tudo que deve ser entregue ou retirado, por período (manhã/tarde) e por veículo.

A ordem segue o horário agendado (não otimiza rota). Calcula o peso transportado e o peso ainda disponível no veículo.
"""

import time
from collections import OrderedDict
from decimal import Decimal

from django.utils import timezone

from .geo import ensure_task_coordinates, origin_point
from .services import task_items
from .models import TransportTask

MORNING, AFTERNOON = "MORNING", "AFTERNOON"
PERIOD_LABELS = {MORNING: "Manhã", AFTERNOON: "Tarde"}
NOON_HOUR = 12


def _num(value):
    return float(value) if value is not None else None


def period_of(moment):
    return MORNING if timezone.localtime(moment).hour < NOON_HOUR else AFTERNOON


def serialize_stop(task, can_view_phone=False, geocode=True):
    quote = task.quote
    items, total, missing = [], Decimal("0"), 0
    for line in task_items(task):
        equipment = line.equipment
        weight = equipment.estimated_weight_kg
        if weight is None:
            missing += 1
        else:
            total += weight
        items.append({"code": equipment.internal_code, "name": equipment.name, "weight_kg": _num(weight)})
    coords = ensure_task_coordinates(task, allow_network=geocode)
    local = timezone.localtime(task.scheduled_at)
    return {
        "id": task.pk, "time": local.strftime("%H:%M"), "scheduled_at": task.scheduled_at.isoformat(),
        "period": period_of(task.scheduled_at), "leg": task.leg, "action_label": "ENTREGAR" if task.leg == TransportTask.Leg.DELIVERY else "RETIRAR",
        "leg_label": task.get_leg_display(), "status": task.status, "status_label": task.get_status_display(),
        "quote_number": quote.number, "customer_name": quote.customer.name,
        "customer_phone": (quote.customer.phone or "") if can_view_phone else "",
        "address": task.address, "complement": task.complement, "notes": task.notes,
        "latitude": coords[0] if coords else None, "longitude": coords[1] if coords else None,
        "vehicle": task.vehicle_id, "vehicle_plate": task.vehicle.plate if task.vehicle else "",
        "driver_name": task.driver.full_name if task.driver else "",
        "weight_kg": float(total), "items_without_weight": missing, "items": items,
    }


def _load_profile(stops, capacity):
    """Simula a carga a bordo: sai do depósito com o que será entregue; entrega descarrega, retirada carrega."""
    initial = sum(s["weight_kg"] for s in stops if s["leg"] == TransportTask.Leg.DELIVERY)
    load = peak = initial
    for stop in stops:
        load += -stop["weight_kg"] if stop["leg"] == TransportTask.Leg.DELIVERY else stop["weight_kg"]
        peak = max(peak, load)
    delivery = initial
    pickup = sum(s["weight_kg"] for s in stops if s["leg"] == TransportTask.Leg.RETURN)
    return {
        "delivery_kg": round(delivery, 2), "pickup_kg": round(pickup, 2), "initial_load_kg": round(initial, 2),
        "peak_load_kg": round(peak, 2), "final_load_kg": round(load, 2),
        "capacity_kg": capacity,
        "remaining_at_departure_kg": round(capacity - initial, 2) if capacity else None,
        "remaining_kg": round(capacity - peak, 2) if capacity else None,
        "overloaded": bool(capacity and peak > capacity),
        "items_without_weight": sum(s["items_without_weight"] for s in stops),
        "stops": len(stops),
    }


def build_day_plan(queryset, day, can_view_phone=False, geocode=True):
    tasks = list(queryset.filter(scheduled_at__date=day).exclude(status=TransportTask.Status.CANCELLED)
                 .select_related("quote__customer", "vehicle", "driver")
                 .prefetch_related("quote__items__equipment", "rental_items__equipment").order_by("scheduled_at", "load_sequence", "pk"))
    # Geocodifica todas as paradas de uma vez (1 consulta/s). O que for resolvido fica salvo; se estourar o tempo, o restante
    # é concluído na próxima consulta — o painel repete a chamada sozinho até todas as paradas terem ponto no mapa.
    deadline = time.monotonic() + 25
    stops = [serialize_stop(task, can_view_phone, geocode and time.monotonic() < deadline) for task in tasks]
    periods = OrderedDict((key, {"key": key, "label": PERIOD_LABELS[key], "stops": []}) for key in (MORNING, AFTERNOON))
    for stop in stops:
        periods[stop["period"]]["stops"].append(stop)
    vehicles = OrderedDict()
    for task, stop in zip(tasks, stops):
        key = task.vehicle_id or 0
        entry = vehicles.setdefault(key, {
            "vehicle": task.vehicle_id, "plate": task.vehicle.plate if task.vehicle else "",
            "label": str(task.vehicle) if task.vehicle else "Sem veículo definido",
            "capacity_kg": task.vehicle.capacity_kg if task.vehicle else None, "stops": [],
        })
        entry["stops"].append(stop)
    vehicle_rows = []
    for entry in vehicles.values():
        profile = {}
        for key in (MORNING, AFTERNOON):
            period_stops = [s for s in entry["stops"] if s["period"] == key]
            profile[key] = _load_profile(period_stops, entry["capacity_kg"]) if period_stops else None
        vehicle_rows.append({**{k: v for k, v in entry.items() if k != "stops"}, "periods": profile, "stops": [s["id"] for s in entry["stops"]]})
    return {
        "date": str(day), "origin": origin_point(),
        "summary": {
            "total": len(stops), "deliveries": sum(s["leg"] == TransportTask.Leg.DELIVERY for s in stops),
            "pickups": sum(s["leg"] == TransportTask.Leg.RETURN for s in stops),
            "morning": len(periods[MORNING]["stops"]), "afternoon": len(periods[AFTERNOON]["stops"]),
            "without_coordinates": sum(s["latitude"] is None for s in stops),
        },
        "periods": list(periods.values()), "vehicles": vehicle_rows, "stops": stops,
    }
