from .models import TransportTask


def ensure_transport_task(quote, leg, created_by):
    required = (
        quote.delivery_transport_required
        if leg == TransportTask.Leg.DELIVERY
        else quote.return_transport_required
    )
    if not required:
        return None
    address = quote.delivery_address if leg == TransportTask.Leg.DELIVERY else quote.return_address
    task, _ = TransportTask.objects.get_or_create(
        quote=quote,
        leg=leg,
        defaults={"address": address, "created_by": created_by},
    )
    return task


def transport_completed(quote, leg):
    return TransportTask.objects.filter(
        quote=quote, leg=leg, status=TransportTask.Status.COMPLETED
    ).exists()
