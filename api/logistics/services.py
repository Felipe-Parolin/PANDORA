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
    complement = quote.delivery_complement if leg == TransportTask.Leg.DELIVERY else quote.return_complement
    task, _ = TransportTask.objects.get_or_create(
        quote=quote,
        leg=leg,
        defaults={"address": address, "complement": complement, "created_by": created_by},
    )
    return task


def transport_completed(quote, leg):
    return TransportTask.objects.filter(
        quote=quote, leg=leg, status=TransportTask.Status.COMPLETED
    ).exists()


def trip_readiness(task):
    """Explain the next action; start/complete actions still enforce all rules."""
    from rentals.models import RentalInspection, RentalQuote
    from rentals.services import availability_reason
    from maintenance.models import ServiceOrder
    from .models import Vehicle

    def state(code, label, detail):
        return {"code": code, "label": label, "detail": detail, "can_start": code == "READY"}

    delivery = task.leg == TransportTask.Leg.DELIVERY
    if task.status == TransportTask.Status.CANCELLED:
        return state("CANCELLED", "Cancelada", "Esta viagem foi cancelada.")
    if task.status == TransportTask.Status.COMPLETED:
        expected = RentalQuote.Status.APPROVED if delivery else RentalQuote.Status.ACTIVE
        if task.quote.status == expected:
            return state("CONFIRM", "Falta confirmar na locação", "Viagem concluída. Confirme a entrega ou o recebimento para atualizar a locação.")
        return state("COMPLETED", "Concluída", "Entrega registrada na locação." if delivery else "Equipamentos recebidos; a avaliação final fica na Manutenção.")
    if task.status == TransportTask.Status.IN_TRANSIT:
        return state("IN_TRANSIT", "Em entrega" if delivery else "Em coleta", "Confirme ao entregar ao cliente." if delivery else "Confirme ao receber os equipamentos de volta no depósito.")
    expected = RentalQuote.Status.APPROVED if delivery else RentalQuote.Status.ACTIVE
    if task.quote.status != expected:
        return state("BLOCKED", "Aguardando locação", "A locação ainda não está na etapa desta viagem.")
    if delivery:
        lines = list(task.quote.items.all())
        equipment_ids = {line.equipment_id for line in lines}
        inspections = [item for item in task.quote.inspections.all() if item.inspection_type == RentalInspection.Type.PRE_RENTAL and item.equipment_id in equipment_ids]
        pending = [item for item in inspections if item.result not in {RentalInspection.Result.APPROVED, RentalInspection.Result.APPROVED_WITH_NOTES}
                   or item.critical_impediment or not (getattr(item, "service_order", None) and item.service_order.status == ServiceOrder.Status.COMPLETED and item.service_order.released)]
        if not lines or len(inspections) != len(lines) or pending:
            return state("BLOCKED", "Aguardando manutenção", "A Manutenção precisa liberar todos os equipamentos. Você já pode planejar a viagem.")
        if any(availability_reason(line.equipment, task.quote.start_date, task.quote.end_date, task.quote) for line in lines):
            return state("BLOCKED", "Equipamento indisponível", "Revise as pendências do equipamento antes da saída.")
    missing = [label for label, value in (("veículo", task.vehicle_id), ("motorista", task.driver_id), ("horário", task.scheduled_at)) if not value]
    if missing:
        return state("PLANNING", "A programar", f"Defina {', '.join(missing)} para liberar a saída.")
    if task.vehicle.status != Vehicle.Status.AVAILABLE or task.vehicle.transport_tasks.filter(status=TransportTask.Status.IN_TRANSIT).exists():
        return state("BLOCKED", "Veículo indisponível", "Escolha um veículo disponível para esta viagem.")
    if not task.driver.is_active or task.driver.driving_tasks.filter(status=TransportTask.Status.IN_TRANSIT).exists():
        return state("BLOCKED", "Motorista indisponível", "Escolha um motorista ativo e sem outra viagem em andamento.")
    return state("READY", "Pronta para sair", "Planejamento completo e equipamentos liberados.")
