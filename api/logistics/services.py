from collections import defaultdict
from datetime import datetime
from django.utils import timezone
from .models import TransportTask
from rentals.addresses import item_destination


def task_items(task):
    owner, name = (task, "rental_items") if task.items_scoped else (task.quote, "items")
    cached = getattr(owner, "_prefetched_objects_cache", {}).get(name)
    return cached if cached is not None else getattr(owner, name).select_related("equipment")


def ensure_transport_task(quote, leg, created_by, items=None, exclude_merge_ids=None):
    required = quote.delivery_transport_required if leg == "DELIVERY" else quote.return_transport_required
    if not required:
        return None
    lines = list(items) if items is not None else list(quote.items.filter(stage="PENDING" if leg == "DELIVERY" else "DELIVERED"))
    if not lines:
        return None
    tasks = list(quote.transport_tasks.filter(leg=leg).exclude(status="CANCELLED"))
    assigned = {line.pk for task in tasks for line in task_items(task)}
    groups = defaultdict(list)
    destinations = {}
    for line in lines:
        if line.pk not in assigned:
            destination = item_destination(quote, line, leg)
            key = (destination['date'], ' '.join(destination['address'].casefold().split()), destination['complement'].strip(), destination['cep'], destination['scheduled_at'])
            groups[key].append(line)
            destinations[key] = destination
    result = tasks[0] if tasks else None
    for key, selected in groups.items():
        day, address_key, complement, cep, schedule = key
        destination = destinations[key]
        task = next((task for task in tasks if task.batch_date == day and task.status == "PLANNED" and task.items_scoped and task.pk not in (exclude_merge_ids or set()) and ' '.join(task.address.casefold().split()) == address_key and task.complement.strip() == complement and task.address_cep == cep and task.scheduled_at == schedule), None)
        if task is None:
            number = quote.transport_tasks.filter(leg=leg, batch_date=day).count()+1
            task = TransportTask.objects.create(quote=quote, leg=leg, batch_date=day, batch_key=f"{day}:{number}", items_scoped=True, address=destination['address'], address_cep=cep, complement=complement, created_by=created_by, scheduled_at=schedule)
            tasks.append(task)
        task.rental_items.add(*selected)
        result = result or task
    return result


def transport_completed(quote, leg, items=None):
    tasks = quote.transport_tasks.filter(leg=leg, status="COMPLETED")
    if items is None:
        # Compatibilidade com os chamadores que verificam o trecho completo.
        lines = list(quote.items.all())
    else:
        lines = list(items)
    completed_ids = {line.pk for task in tasks for line in task_items(task)}
    return bool(lines) and all(line.pk in completed_ids for line in lines)
