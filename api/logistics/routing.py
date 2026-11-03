"""Distância viária por OSRM, sem substituição por distância em linha reta."""

import hashlib
import json
import math
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


_lock = threading.Lock()
_last_call = 0.0


def road_route(origin, destination):
    """Recebe (latitude, longitude); retorna metros/segundos ou None, em falhas."""
    global _last_call
    base = settings.FREIGHT_ROUTING_URL.rstrip("/")
    if not base:
        return None
    coordinates = ";".join(f"{lng:.7f},{lat:.7f}" for lat, lng in (origin, destination))
    url = f"{base}/route/v1/driving/{coordinates}?overview=false&steps=false&alternatives=false&radiuses=500;500"
    key = "pandora:road-route:" + hashlib.sha256(url.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    try:
        # O servidor público permite até uma consulta por segundo. Cache evita repetições.
        if urlsplit(base).hostname in {"router.project-osrm.org", "routing.openstreetmap.de"}:
            with _lock:
                wait = 1.1 - (time.monotonic() - _last_call)
                if wait > 0:
                    time.sleep(wait)
                _last_call = time.monotonic()
        request = Request(url, headers={"User-Agent": "PANDORA/1.0 (equipment-rental routing)", "Accept": "application/json"})
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read(65536))
        if data.get("code") != "Ok":
            raise ValueError("Rota indisponível")
        route = data["routes"][0]
        distance, duration = float(route["distance"]), float(route["duration"])
        waypoints = data["waypoints"]
        if len(waypoints) != 2 or any(not 0 <= float(point["distance"]) <= 500 for point in waypoints):
            raise ValueError("Ponto distante da malha viária")
        if not all(math.isfinite(value) and value >= 0 for value in (distance, duration)):
            raise ValueError("Distância ou duração inválida")
        result = {"distance_m": distance, "duration_seconds": duration}
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        cache.set(key, {}, 30)
        return None
    cache.set(key, result, 60 * 60 * 24)
    return result
