"""Geocodificação leve (OpenStreetMap/Nominatim + CEP via BrasilAPI) para o mapa do roteiro.

Nunca bloqueia a operação: sem coordenadas, a parada continua na lista e apenas não aparece no mapa.
"""

import json
import hashlib
import logging
import math
import re
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Centro de Leme/SP: usado apenas se nem o CEP de origem puder ser consultado.
FALLBACK_ORIGIN = (-22.1853, -47.3903)
USER_AGENT = "PANDORA/1.0 (roteiro de entregas; contato interno)"

# O Nominatim permite no máximo 1 consulta por segundo; em rajada ele recusa (429) e as paradas ficam sem ponto no mapa.
_throttle_lock = threading.Lock()
_last_call = 0.0


def _throttle():
    global _last_call
    with _throttle_lock:
        wait = 1.1 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _valid_brazil(lat, lng):
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lat, lng)) and -34 <= lat <= 6 and -74 <= lng <= -34


def _nominatim(query):
    key = "pandora:geo:" + re.sub(r"\s+", " ", query.strip().lower())[:180]
    cached = cache.get(key)
    if cached is not None:
        return tuple(cached) if cached else None
    url = settings.GEOCODING_SEARCH_URL + "?" + urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "br"})
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        _throttle()
        with urlopen(request, timeout=6) as response:
            data = json.loads(response.read(65536))
        if isinstance(data, list) and data:
            lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
            if _valid_brazil(lat, lng):
                cache.set(key, [lat, lng], 60 * 60 * 24 * 30)
                return lat, lng
        cache.set(key, [], 60 * 60 * 6)
    except Exception as exc:  # rede indisponível, limite de uso, resposta inesperada...
        logger.info("Geocodificação indisponível (%s).", type(exc).__name__)
    return None


def _from_cep(cep):
    digits = re.sub(r"\D", "", str(cep or ""))
    if len(digits) != 8:
        return None
    try:
        from rentals.freight import lookup_cep
        data = lookup_cep(digits)
        if data.get("latitude") is not None and data.get("longitude") is not None:
            return float(data["latitude"]), float(data["longitude"])
    except Exception as exc:
        logger.info("CEP sem coordenadas (%s).", type(exc).__name__)
    return None


def _address_candidates(address, cep):
    """Consultas do mais específico ao mais genérico, para que a parada apareça no mapa mesmo sem número exato."""
    address = re.sub(r"\s+", " ", str(address or "")).strip()
    digits = re.sub(r"\D", "", str(cep or "")) or (re.search(r"\b(\d{5})-?(\d{3})\b", address) and "".join(re.search(r"\b(\d{5})-?(\d{3})\b", address).groups())) or ""
    candidates = []
    if address:
        candidates.append(address)
        parts = [part.strip() for part in address.split(",") if part.strip()]
        if len(parts) > 3:
            candidates.append(", ".join(parts[:1] + parts[-2:]))  # rua + cidade/UF/CEP, sem número e complemento
        elif len(parts) > 2:
            candidates.append(", ".join(parts[-2:]))  # cidade/UF/CEP
    if len(digits) == 8:
        candidates.append(f"{digits[:5]}-{digits[5:]}")
    seen, unique = set(), []
    for item in candidates:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:3]


def geocode_address(address, cep=""):
    """Retorna (lat, lng) ou None. Tenta o endereço completo, versões mais genéricas e, por fim, o CEP."""
    if not getattr(settings, "GEOCODING_ENABLED", True):
        return _from_cep(cep)
    for query in _address_candidates(address, cep):
        found = _nominatim(f"{query}, Brasil" if "brasil" not in query.lower() else query)
        if found:
            return found
    return _from_cep(cep)


def geocode_precise_address(address, *, number="", destination=None):
    """Para cobrar frete, exige o número localizado; não usa centro da rua/cidade/CEP."""
    if not address or not getattr(settings, "GEOCODING_ENABLED", True):
        return None
    query = re.sub(r"\s+", " ", address.strip())
    from rentals.addresses import split_address
    base_address, legacy_number = split_address(query)
    expected_number = str(number or legacy_number).strip()
    base = settings.GEOCODING_SEARCH_URL
    key = "pandora:geo-precise-v2:" + hashlib.sha256(f"{base}:{query.lower()}:{expected_number}:{destination}".encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return tuple(cached) if cached else None
    params = {"format": "json", "limit": 3, "countrycodes": "br", "addressdetails": 1}
    if destination and expected_number and destination.get("street"):
        params.update(street=f"{expected_number} {base_address.split(',')[0].strip()}", city=destination.get('city',''), state=destination.get('state',''), country="Brasil", postalcode=destination.get('cep',''))
    else:
        params["q"] = query
    url = base + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        _throttle()
        with urlopen(request, timeout=6) as response:
            data = json.loads(response.read(65536))
        for point in data if isinstance(data, list) else []:
            found_number = str(point.get("address", {}).get("house_number") or "").strip()
            lat, lng = float(point["lat"]), float(point["lon"])
            matches = found_number.casefold() == expected_number.casefold() if expected_number else found_number and re.search(rf"(?<!\w){re.escape(found_number)}(?!\w)", query, re.IGNORECASE)
            if found_number and matches and _valid_brazil(lat, lng):
                cache.set(key, [lat, lng], 60 * 60 * 24 * 30)
                return lat, lng
        cache.set(key, [], 60 * 10)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        cache.set(key, [], 30)
    return None


def origin_point():
    """Mesmo depósito do frete; fallback aproximado permanece apenas no mapa."""
    from rentals.freight import freight_origin
    found = freight_origin()
    exact = found is not None
    found = found or _from_cep(getattr(settings, "FREIGHT_ORIGIN_CEP", ""))
    lat, lng = found or FALLBACK_ORIGIN
    return {"label": getattr(settings, "FREIGHT_ORIGIN_LABEL", "") or "Depósito (saída)", "latitude": lat, "longitude": lng,
            "provisional": not exact}


def ensure_task_coordinates(task, allow_network=True):
    """Preenche latitude/longitude da viagem (e guarda para não consultar de novo enquanto o endereço não mudar)."""
    if task.latitude is not None and task.longitude is not None and task.geocoded_address == task.address:
        return task.latitude, task.longitude
    if not allow_network:
        return None
    cep = task.address_cep
    found = geocode_address(task.address, cep)
    if found:
        task.latitude, task.longitude = found
        task.geocoded_address = task.address
        task.save(update_fields=("latitude", "longitude", "geocoded_address"))
        return found
    return None
