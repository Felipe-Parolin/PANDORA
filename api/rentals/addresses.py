"""Endereços de locação: número separado e destino efetivo de cada item."""
import re
from datetime import datetime, time
from django.utils import timezone


def split_address(address):
    parts = [part.strip() for part in str(address or "").split(",")]
    if len(parts) > 1 and re.fullmatch(r"(?:\d+[A-Za-z]?(?:[-/]\d+)?|s/?n)", parts[1], re.I):
        return ", ".join([parts[0], *parts[2:]]), parts[1]
    return str(address or "").strip(), ""


def full_address(address, number=""):
    if not number:
        return str(address or "").strip()
    base, _ = split_address(address)
    parts = base.split(",", 1)
    return ", ".join(filter(None, [parts[0].strip(), str(number).strip(), parts[1].strip() if len(parts) > 1 else ""]))


def item_destination(quote, line, leg):
    prefix = "delivery" if leg == "DELIVERY" else "return"
    custom = getattr(line, f"{prefix}_location", None) or {}
    requested = getattr(quote, f"requested_{prefix}_at")
    clock = time.fromisoformat(custom['time']) if custom and custom.get('time') else None
    if not custom and requested:
        clock = timezone.localtime(requested).time()
    day = line.start_date if leg == "DELIVERY" else line.end_date
    schedule = timezone.make_aware(datetime.combine(day, clock)) if clock is not None else None
    address = custom.get("address", getattr(quote, f"{prefix}_address"))
    number = custom.get("number", getattr(quote, f"{prefix}_number", ""))
    return {"date": day, "address": full_address(address, number), "number": number,
            "cep": custom.get("cep", getattr(quote, f"{prefix}_cep")),
            "complement": custom.get("complement", getattr(quote, f"{prefix}_complement")), "scheduled_at": schedule}
