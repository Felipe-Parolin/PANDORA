"""Indicador de recorrência e risco (RI4 / RF35), explicável e sem uso de LLM.

Combina frequência de falhas, gravidade e tempo desde a última manutenção para *priorizar a
análise humana*. Não altera prioridade, diagnóstico nem situação do equipamento (RN7).
"""
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from django.utils import timezone

from assets.models import Equipment
from maintenance.models import MaintenancePlan, ServiceOrder
from maintenance.services import maintenance_alert_status

from .text import tokenize

FAILURE_TYPES = (ServiceOrder.Type.CORRECTIVE,)
SEVERITY_WEIGHT = {"CRÍTICA": 1.0, "ALTA": 0.7}


@dataclass
class RiskMetrics:
    window_days: int
    failures: int
    severity_units: float
    abandoned_or_waiting: int
    days_since_service: int | None
    overdue_plans: int
    recurring_terms: list[str] = field(default_factory=list)
    last_failure_date: str | None = None


@dataclass
class RiskAssessment:
    equipment_id: int
    equipment_name: str
    internal_code: str
    score: int
    level: str
    level_label: str
    factors: list[dict]
    metrics: dict


class RiskScoringStrategy(ABC):
    @abstractmethod
    def assess(self, metrics: RiskMetrics) -> tuple[int, list[dict]]: ...


class WeightedRiskStrategy(RiskScoringStrategy):
    """45 pts frequência + 30 pts gravidade + 25 pts tempo/planos vencidos."""

    FREQUENCY_MAX, SEVERITY_MAX, TIME_MAX = 45, 30, 25
    MAX_FAILURES, SEVERITY_CAP, GAP_DAYS = 5, 3.0, 365

    def assess(self, m):
        frequency = round(min(m.failures, self.MAX_FAILURES) / self.MAX_FAILURES * self.FREQUENCY_MAX)
        severity = round(min(m.severity_units, self.SEVERITY_CAP) / self.SEVERITY_CAP * self.SEVERITY_MAX)
        gap_days = m.days_since_service if m.days_since_service is not None else self.GAP_DAYS
        gap = round(min(gap_days, self.GAP_DAYS) / self.GAP_DAYS * 15)
        overdue = 10 if m.overdue_plans else 0
        factors = [
            {"key": "frequency", "label": "Frequência de falhas", "points": frequency, "max": self.FREQUENCY_MAX,
             "detail": f"{m.failures} chamado(s) corretivo(s) em {m.window_days} dias"},
            {"key": "severity", "label": "Gravidade", "points": severity, "max": self.SEVERITY_MAX,
             "detail": f"{m.abandoned_or_waiting} chamado(s) abandonado(s)/aguardando peças; prioridades alta/crítica pesam mais"},
            {"key": "time", "label": "Tempo desde a última manutenção", "points": gap + overdue, "max": self.TIME_MAX,
             "detail": ("Sem manutenção concluída registrada" if m.days_since_service is None else f"{m.days_since_service} dias desde a última manutenção")
                       + (f"; {m.overdue_plans} plano(s) vencido(s)" if m.overdue_plans else "")},
        ]
        return min(sum(f["points"] for f in factors), 100), factors


LEVELS = ((60, "HIGH", "Alto"), (30, "MEDIUM", "Médio"), (0, "LOW", "Baixo"))


def level_for(score: int):
    return next((code, label) for floor, code, label in LEVELS if score >= floor)


class RiskAnalyzer:
    def __init__(self, strategy: RiskScoringStrategy | None = None, window_days: int = 180):
        self.strategy = strategy or WeightedRiskStrategy()
        self.window_days = window_days

    def metrics_for(self, equipment) -> RiskMetrics:
        now = timezone.now()
        since = now - timedelta(days=self.window_days)
        orders = list(ServiceOrder.objects.filter(equipment=equipment, maintenance_type__in=FAILURE_TYPES, opened_at__gte=since).order_by("-opened_at"))
        severity = sum(
            min(SEVERITY_WEIGHT.get(o.priority, 0.4) + (0.3 if o.status in (ServiceOrder.Status.ABANDONED, ServiceOrder.Status.WAITING_PARTS) else 0), 1.0)
            for o in orders
        )
        last_done = (
            ServiceOrder.objects.filter(equipment=equipment, status=ServiceOrder.Status.COMPLETED, closed_at__isnull=False)
            .exclude(maintenance_type__in=(ServiceOrder.Type.PRE_RENTAL, ServiceOrder.Type.POST_RENTAL))
            .order_by("-closed_at").values_list("closed_at", flat=True).first()
        )
        if last_done is None and equipment.acquisition_date and (timezone.localdate() - equipment.acquisition_date).days < self.strategy.GAP_DAYS:
            days_since = (timezone.localdate() - equipment.acquisition_date).days  # equipamento novo ainda não "venceu" por falta de histórico
        else:
            days_since = (now - last_done).days if last_done else None
        plans = MaintenancePlan.objects.filter(equipment=equipment, active=True).select_related("equipment")
        overdue = sum(maintenance_alert_status(plan) in {"OVERDUE", "CRITICAL"} for plan in plans)
        term_counter = Counter()
        for order in orders:
            term_counter.update(set(tokenize(order.symptoms)))
        recurring = [term for term, count in term_counter.most_common(8) if count >= 2][:5]
        return RiskMetrics(
            window_days=self.window_days, failures=len(orders), severity_units=severity,
            abandoned_or_waiting=sum(o.status in (ServiceOrder.Status.ABANDONED, ServiceOrder.Status.WAITING_PARTS) for o in orders),
            days_since_service=days_since, overdue_plans=overdue, recurring_terms=recurring,
            last_failure_date=orders[0].opened_at.date().isoformat() if orders else None,
        )

    def assess(self, equipment) -> RiskAssessment:
        metrics = self.metrics_for(equipment)
        score, factors = self.strategy.assess(metrics)
        level, label = level_for(score)
        return RiskAssessment(equipment.pk, equipment.name, equipment.internal_code, score, level, label, factors, asdict(metrics))

    def ranking(self, limit: int | None = None, include_inactive=False) -> list[RiskAssessment]:
        queryset = Equipment.objects.all() if include_inactive else Equipment.objects.exclude(status=Equipment.Status.INACTIVE)
        ranked = sorted((self.assess(e) for e in queryset), key=lambda a: (-a.score, a.internal_code))
        return ranked[:limit] if limit else ranked
