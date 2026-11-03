import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from assets.models import MediaAsset
from core.models import Notification
from core.notifications import notify, users_with_acl
from maintenance.models import ServiceOrder

from .knowledge import index_media, is_indexable
from .risk import RiskAnalyzer

logger = logging.getLogger(__name__)


@receiver(post_save, sender=MediaAsset)
def index_manual_on_upload(sender, instance, created, **kwargs):
    """Mantém o índice de consulta atualizado; falhas nunca bloqueiam o envio do arquivo."""
    if not is_indexable(instance):
        return
    try:
        index_media(instance)
    except Exception:  # pragma: no cover - defesa adicional
        logger.exception("Falha ao indexar o manual %s", instance.pk)


@receiver(post_save, sender=ServiceOrder)
def alert_high_recurrence_risk(sender, instance, created, **kwargs):
    """Alerta técnicos e gestores quando um equipamento entra em risco alto de recorrência."""
    if instance.maintenance_type != ServiceOrder.Type.CORRECTIVE:
        return
    try:
        assessment = RiskAnalyzer().assess(instance.equipment)
        if assessment.level != "HIGH":
            return
        notify(
            users_with_acl("ai.assist"), kind=Notification.Kind.MAINTENANCE,
            title=f"Risco de recorrência alto: {instance.equipment.name}",
            message=f"Indicador {assessment.score}/100. Reveja o histórico antes de liberar o equipamento.",
            target_url=f"/manutencao?order={instance.pk}",
            event_key=f"risk:{instance.equipment_id}:high:{assessment.metrics['failures']}",
        )
    except Exception:  # pragma: no cover - alerta é complementar
        logger.exception("Falha ao avaliar risco do equipamento %s", instance.equipment_id)
