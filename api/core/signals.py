from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from logistics.models import TransportTask
from maintenance.models import ServiceOrder
from rentals.models import RentalQuote

from .models import Notification
from .notifications import notify, users_with_acl


def remember_previous(sender, instance, **kwargs):
    fields = ("status", "technician_id") if sender is ServiceOrder else ("status",)
    instance._previous_state = sender.objects.filter(pk=instance.pk).values(*fields).first() if instance.pk else None


@receiver(pre_save, sender=ServiceOrder)
def before_order_save(sender, instance, **kwargs):
    remember_previous(sender, instance)


@receiver(pre_save, sender=RentalQuote)
def before_quote_save(sender, instance, **kwargs):
    remember_previous(sender, instance)


@receiver(pre_save, sender=TransportTask)
def before_task_save(sender, instance, **kwargs):
    remember_previous(sender, instance)


@receiver(post_save, sender=ServiceOrder)
def order_notification(sender, instance, created, **kwargs):
    previous = instance._previous_state or {}
    if created:
        notify(
            users_with_acl("maintenance.view"), kind=Notification.Kind.MAINTENANCE,
            title=f"Novo chamado {instance.number}",
            message=f"{instance.equipment.name}: {instance.get_maintenance_type_display()}.",
            target_url=f"/manutencao?order={instance.pk}", event_key=f"order:{instance.pk}:created",
        )
    if instance.technician_id and previous.get("technician_id") != instance.technician_id:
        notify(
            [instance.technician], kind=Notification.Kind.MAINTENANCE,
            title=f"Chamado atribuído: {instance.number}",
            message=f"Você é responsável pelo atendimento de {instance.equipment.name}.",
            target_url=f"/manutencao?order={instance.pk}", event_key=f"order:{instance.pk}:assigned:{instance.technician_id}",
        )
    if not created and previous.get("status") != instance.status and instance.status == ServiceOrder.Status.COMPLETED:
        quote = instance.rental_inspection.quote if instance.rental_inspection_id else None
        recipients = [quote.created_by] if quote else users_with_acl("maintenance.view")
        notify(
            recipients, kind=Notification.Kind.MAINTENANCE,
            title=f"Chamado concluído: {instance.number}",
            message=f"{instance.equipment.name} teve o atendimento concluído.",
            target_url=f"/locacoes?quote={quote.number}" if quote else f"/manutencao?order={instance.pk}",
            event_key=f"order:{instance.pk}:completed",
        )


@receiver(post_save, sender=RentalQuote)
def quote_notification(sender, instance, created, **kwargs):
    previous = instance._previous_state or {}
    if created or previous.get("status") == instance.status:
        return
    if instance.status == RentalQuote.Status.APPROVED:
        recipients = users_with_acl("maintenance.view")
        title, message = f"Reserva aprovada: {instance.number}", "Faça as inspeções pré-locação antes da entrega."
    elif instance.status == RentalQuote.Status.RETURNED:
        recipients = users_with_acl("maintenance.view")
        title, message = f"Devolução registrada: {instance.number}", "A inspeção final foi encaminhada para a manutenção."
    elif instance.status == RentalQuote.Status.COMPLETED:
        recipients = [instance.created_by]
        title, message = f"Locação concluída: {instance.number}", "A devolução e as inspeções foram finalizadas."
    else:
        return
    notify(recipients, kind=Notification.Kind.RENTAL, title=title, message=message,
           target_url=f"/manutencao?quote={instance.number}" if instance.status == RentalQuote.Status.RETURNED else f"/locacoes?quote={instance.number}",
           event_key=f"quote:{instance.pk}:{instance.status.lower()}")


@receiver(post_save, sender=TransportTask)
def transport_notification(sender, instance, created, **kwargs):
    previous = instance._previous_state or {}
    if created:
        notify(users_with_acl("logistics.view"), kind=Notification.Kind.TRANSPORT,
               title=f"Viagem a planejar: {instance.quote.number}",
               message=f"{instance.get_leg_display()} precisa de veículo e programação.",
               target_url="/transporte", event_key=f"transport:{instance.pk}:created")
    elif previous.get("status") != instance.status and instance.status == TransportTask.Status.COMPLETED:
        notify([instance.quote.created_by], kind=Notification.Kind.TRANSPORT,
               title=f"Viagem concluída: {instance.quote.number}",
               message=f"{instance.get_leg_display()} registrada como concluída.",
               target_url="/transporte", event_key=f"transport:{instance.pk}:completed")
