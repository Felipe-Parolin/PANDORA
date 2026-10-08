"""CEP lookup and an explicitly approximate, configurable freight simulation."""

import json
import math
import re
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


def estimate_freight(destination):
    """Estimate one trip from the configured origin; never claim road-route accuracy."""
    origin_cep = settings.FREIGHT_ORIGIN_CEP
    try:
        origin = lookup_cep(origin_cep)
    except (ValidationError, AddressProviderUnavailable):
        return {"fee": None, "distance_km": None, "reason": "CEP de origem indisponível; informe o frete manualmente."}
    if None in (origin["latitude"], origin["longitude"], destination["latitude"], destination["longitude"]):
        return {"fee": None, "distance_km": None, "reason": "Este CEP não tem coordenadas confiáveis; informe o frete manualmente."}

    lat1, lon1, lat2, lon2 = map(math.radians, (
        origin["latitude"], origin["longitude"], destination["latitude"], destination["longitude"],
    ))
    arc = 2 * math.asin(min(1, math.sqrt(math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)))
    approximate_km = Decimal(str(6371 * arc)) * settings.FREIGHT_ROAD_FACTOR
    fee = max(settings.FREIGHT_MINIMUM_PER_LEG, approximate_km * settings.FREIGHT_RATE_PER_KM)
    return {
        "fee": str(fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "distance_km": str(approximate_km.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
        "origin_label": settings.FREIGHT_ORIGIN_LABEL,
        "provisional_origin": settings.FREIGHT_ORIGIN_PROVISIONAL,
        "method": "Distância em linha reta com fator de ajuste; não é rota viária nem tarifa oficial.",
    }
