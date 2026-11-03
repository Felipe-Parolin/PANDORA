"""Consulta de CEP e frete calculado pela rota viária e pela tarifa configurada."""

import json
import math
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import APIException, ValidationError


class AddressProviderUnavailable(APIException):
    status_code = 503
    default_detail = "A consulta de CEP está indisponível. Informe o endereço e o frete manualmente."


def lookup_cep(raw_cep):
    cep = re.sub(r"\D", "", str(raw_cep or ""))
    if len(cep) != 8:
        raise ValidationError({"cep": "Informe um CEP com 8 dígitos."})

    cache_key = f"pandora:cep-v2:{cep}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    request = Request(
        f"https://brasilapi.com.br/api/cep/v2/{cep}",
        headers={"User-Agent": "PANDORA/1.0 (equipment-rental address lookup)", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=7) as response:
            data = json.loads(response.read(65536))
    except HTTPError as exc:
        if exc.code == 404:
            raise ValidationError({"cep": "CEP não encontrado."}) from exc
        raise AddressProviderUnavailable() from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise AddressProviderUnavailable() from exc

    if not isinstance(data, dict):
        raise AddressProviderUnavailable()
    coordinates = (data.get("location") or {}).get("coordinates") or {}
    try:
        latitude = float(coordinates["latitude"])
        longitude = float(coordinates["longitude"])
        if not (math.isfinite(latitude) and math.isfinite(longitude) and -34 <= latitude <= 6 and -74 <= longitude <= -34):
            raise ValueError("Coordenadas fora do Brasil")
    except (KeyError, TypeError, ValueError):
        latitude = longitude = None

    result = {
        "cep": cep,
        "street": data.get("street") or "",
        "neighborhood": data.get("neighborhood") or "",
        "city": data.get("city") or "",
        "state": data.get("state") or "",
        "latitude": latitude,
        "longitude": longitude,
    }
    if not result["city"] or not result["state"]:
        raise AddressProviderUnavailable()
    cache.set(cache_key, result, 60 * 60 * 24)
    return result


def freight_origin():
    """Ponto confirmado do depósito, ou endereço localizado com número exato."""
    from logistics.geo import _valid_brazil, geocode_precise_address
    try:
        lat, lng = float(settings.FREIGHT_ORIGIN_LATITUDE), float(settings.FREIGHT_ORIGIN_LONGITUDE)
        return (lat, lng) if _valid_brazil(lat, lng) else None
    except (ValueError, TypeError):
        return geocode_precise_address(settings.FREIGHT_ORIGIN_ADDRESS)


def approximate_destination(destination, address):
    """CEP de logradouro, somente quando corresponde à rua digitada (nunca centro da cidade)."""
    from logistics.geo import _valid_brazil

    def words(value):
        text = unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode()
        return set(re.findall(r"[a-z0-9]+", text)) - {"avenida", "av", "rua", "r", "rodovia", "rod", "de", "da", "do", "dos", "das"}

    street = words(destination.get("street", ""))
    if not street or not street.issubset(words(address)):
        return None
    lat, lng = destination.get("latitude"), destination.get("longitude")
    return (lat, lng) if _valid_brazil(lat, lng) else None


def estimate_period_freight(destination, periods, **kwargs):
    """Soma os trechos por data, sem reunir cargas de dias diferentes."""
    groups = {}
    field = "start_date" if kwargs.get("leg") == "DELIVERY" else "end_date"
    for item in periods:
        groups.setdefault((item[field], item.get('time','')), []).append(item["equipment_id"])
    batches = []
    for (day, clock), ids in sorted(groups.items()):
        estimate = estimate_freight(destination, ids, **kwargs)
        if estimate.get("fee") is None:
            return estimate
        batches.append({"date": day, "time": clock, "equipment_ids": ids, **estimate})
    return {**batches[0], "fee": str(sum((Decimal(batch["fee"]) for batch in batches), Decimal("0"))),
            "trip_count": sum(batch["trip_count"] for batch in batches), "equipment_count": len(periods),
            "load_method": f"{len(batches)} data(s) de transporte; carga e viagens calculadas separadamente por data.", "batches": batches}


def estimate_freight(destination, equipment_ids=None, *, address="", number="", leg="DELIVERY", allow_approximate=True):
    """Entrega: depósito → cliente. Coleta: cliente → depósito. Sem fallback fictício."""
    from logistics.geo import geocode_precise_address
    from logistics.routing import road_route

    def unavailable(reason):
        return {"fee": None, "distance_km": None, "reason": reason, "origin_label": settings.FREIGHT_ORIGIN_LABEL}

    if not address.strip():
        return unavailable("Complete o endereço com rua e número para calcular o frete.")
    origin = freight_origin()
    if origin is None:
        return unavailable("Não foi possível localizar o depósito com precisão. Informe o frete manualmente.")
    from .addresses import full_address
    point = geocode_precise_address(full_address(address, number), number=number, destination=destination) if number else geocode_precise_address(address)
    precision = "HOUSE_NUMBER"
    if point is None:
        point = approximate_destination(destination, address)
        if point is None:
            return unavailable("O número não consta no mapa e o CEP não fornece um ponto da mesma rua. Confira rua e CEP ou informe o frete manualmente.")
        if not allow_approximate:
            return {
                **unavailable("O mapa não possui esse número. Há um ponto aproximado da rua pelo CEP; confira sua localização antes de calcular."),
                "requires_location_confirmation": True,
                "destination": {"latitude": point[0], "longitude": point[1]},
                "location_label": f"{destination['street']}, {destination['city']}/{destination['state']} · CEP {destination['cep']}",
            }
        precision = "CEP_STREET"
    route = road_route(point, origin) if leg == "RETURN" else road_route(origin, point)
    if route is None:
        return unavailable("Não foi possível consultar a rota viária. Tente novamente ou informe o frete manualmente.")
    route_km = Decimal(str(route["distance_m"])) / Decimal("1000")
    equipment_ids = list(dict.fromkeys(int(value) for value in (equipment_ids or []) if str(value).isdigit()))
    equipment_count = 0
    trip_count = 1
    load_method = "Sem composição de carga informada; estimativa de uma viagem."
    if equipment_ids:
        from assets.models import Equipment
        selected = list(Equipment.objects.filter(pk__in=equipment_ids).only("id", "estimated_weight_kg"))
        equipment_count = len(selected)
        missing_weights = [item.pk for item in selected if item.estimated_weight_kg is None]
        if selected and not missing_weights:
            from logistics.models import Vehicle
            from django.db.models import Q
            capacities = list(Vehicle.objects.filter(status=Vehicle.Status.AVAILABLE, capacity_kg__isnull=False).exclude(
                transport_tasks__status__in=("PLANNED", "IN_TRANSIT")
            ).distinct().values_list("capacity_kg", flat=True))
            max_capacity = max(capacities) if capacities else None
            total_weight = sum((item.estimated_weight_kg for item in selected), Decimal("0"))
            if max_capacity:
                trip_count = max(1, math.ceil(float(total_weight / Decimal(max_capacity))))
                load_method = f"Carga estimada de {total_weight} kg; capacidade de referência {max_capacity} kg."
            else:
                per_trip = max(1, int(getattr(settings, "FREIGHT_ITEMS_PER_TRIP", 3)))
                trip_count = max(1, math.ceil(equipment_count / per_trip))
                load_method = f"Sem capacidade de veículo cadastrada; estimativa por até {per_trip} equipamentos por viagem."
        else:
            per_trip = max(1, int(getattr(settings, "FREIGHT_ITEMS_PER_TRIP", 3)))
            trip_count = max(1, math.ceil(equipment_count / per_trip))
            load_method = f"Peso ausente em {len(missing_weights)} equipamento(s); estimativa provisória por até {per_trip} equipamentos por viagem."
    distance_component = route_km * settings.FREIGHT_RATE_PER_KM
    distance_component = max(settings.FREIGHT_MINIMUM_PER_LEG, distance_component)
    operational_component = getattr(settings, "FREIGHT_OPERATIONAL_COST_PER_TRIP", Decimal("0.00"))
    extra_component = getattr(settings, "FREIGHT_EXTRA_FEE", Decimal("0.00"))
    city_key = f"{destination.get('city', '').strip().lower()}/{destination.get('state', '').strip().upper()}"
    city_surcharge = Decimal(str(getattr(settings, "FREIGHT_CITY_SURCHARGES", {}).get(city_key, 0) or 0))
    per_trip_fee = distance_component + operational_component + extra_component + city_surcharge
    fee = per_trip_fee * trip_count
    return {
        "fee": str(fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "distance_km": str(route_km.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
        "distance_m": route["distance_m"],
        "duration_minutes": math.ceil(route["duration_seconds"] / 60),
        "route_provider": "OSRM",
        "destination_precision": precision,
        "destination": {"latitude": point[0], "longitude": point[1]},
        "approximate_destination": precision != "HOUSE_NUMBER",
        "leg": leg,
        "trip_count": trip_count,
        "equipment_count": equipment_count,
        "per_trip_fee": str(per_trip_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "breakdown": {
            "distance_component_per_trip": str(distance_component.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "operational_component_per_trip": str(operational_component.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "extra_component_per_trip": str(extra_component.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "city_surcharge_per_trip": str(city_surcharge.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "minimum_per_trip": str(settings.FREIGHT_MINIMUM_PER_LEG),
            "rate_per_km": str(settings.FREIGHT_RATE_PER_KM),
        },
        "load_method": load_method,
        "origin_label": settings.FREIGHT_ORIGIN_LABEL,
        "provisional_origin": False,
        "method": "Distância da rota viária OSRM/OpenStreetMap, sem trânsito em tempo real. Tarifa por trecho e viagem; não inclui retorno vazio ou pedágios não configurados.",
    }
