from abc import ABC, abstractmethod
from dataclasses import dataclass

from .models import ServiceOrder


class ServiceOrderBuilderContract(ABC):
    """Interface do Builder de abertura de ordens de serviço."""

    @abstractmethod
    def reset(self): ...

    @abstractmethod
    def equipment(self, value): ...

    @abstractmethod
    def responsible(self, opened_by, technician=None): ...

    @abstractmethod
    def report(self, symptoms): ...

    @abstractmethod
    def kind(self, maintenance_type): ...

    @abstractmethod
    def build(self, **extra): ...


class ServiceOrderBuilder(ServiceOrderBuilderContract):
    """Concrete Builder que persiste a OS somente após validar as etapas."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._data = {}
        return self

    def equipment(self, value):
        self._data["equipment"] = value
        return self

    def responsible(self, opened_by, technician=None):
        self._data.update(opened_by=opened_by, technician=technician)
        return self

    def report(self, symptoms):
        self._data["symptoms"] = symptoms
        return self

    def kind(self, maintenance_type):
        self._data["maintenance_type"] = maintenance_type
        return self

    def build(self, **extra):
        required = {"equipment", "opened_by", "symptoms", "maintenance_type"}
        missing = required.difference(self._data)
        if missing:
            raise ValueError(f"Campos obrigatórios ausentes: {', '.join(sorted(missing))}")
        order = ServiceOrder.objects.create(**self._data, **extra)
        self.reset()
        return order


class ServiceOrderOpeningDirector:
    """Director que padroniza a sequência de montagem descrita na modelagem."""

    def __init__(self, builder=None):
        self.builder = builder or ServiceOrderBuilder()

    def open(self, *, equipment, opened_by, symptoms, maintenance_type, technician=None, **extra):
        return (
            self.builder.reset()
            .equipment(equipment)
            .responsible(opened_by, technician)
            .report(symptoms)
            .kind(maintenance_type)
            .build(**extra)
        )


class ReportProcessor(ABC):
    @abstractmethod
    def process(self, content): ...


class TextReportProcessor(ReportProcessor):
    def process(self, content):
        return " ".join(content.split()).strip()


@dataclass(frozen=True)
class AudioReport:
    """Conteúdo bruto de um relato por voz (nunca persistido)."""

    content: bytes
    filename: str = "relato.webm"
    content_type: str = "audio/webm"


class AudioReportProcessor(ReportProcessor):
    """Transcreve o áudio; a transcrição deve ser confirmada pelo técnico antes de virar relato."""

    def __init__(self, transcriber=None):
        self._transcriber = transcriber

    def process(self, content):
        transcriber = self._transcriber
        if transcriber is None:
            from ai.providers import get_llm_provider  # import tardio: manutenção não depende da IA

            transcriber = get_llm_provider().transcribe
        return " ".join(transcriber(content.content, content.filename, content.content_type).split())


class ReportProcessorCreator(ABC):
    """Creator do Factory Method; o fluxo comum usa apenas a interface do produto."""

    def process(self, content):
        return self.create_processor().process(content)

    @abstractmethod
    def create_processor(self) -> ReportProcessor: ...


class TextReportProcessorCreator(ReportProcessorCreator):
    def create_processor(self):
        return TextReportProcessor()


class AudioReportProcessorCreator(ReportProcessorCreator):
    def create_processor(self):
        return AudioReportProcessor()

    def create_processor_with(self, transcriber):
        """Variante com transcritor injetado (permite trocar o provedor e testar sem rede)."""
        return AudioReportProcessor(transcriber)


class ReportProcessorFactory:
    """Seletor de creators; mantido como fachada compatível com a API existente."""

    _creators = {
        "text": TextReportProcessorCreator,
        "audio": AudioReportProcessorCreator,
    }

    @classmethod
    def creator(cls, kind):
        try:
            return cls._creators[kind]()
        except KeyError as exc:
            raise ValueError("Formato de relato não suportado.") from exc

    @classmethod
    def create(cls, kind):
        return cls.creator(kind).create_processor()

    @classmethod
    def process(cls, kind, content):
        return cls.creator(kind).process(content)


class MaintenanceChecklist(ABC):
    @abstractmethod
    def items(self) -> tuple[str, ...]: ...


class MaintenanceRoute(ABC):
    @abstractmethod
    def steps(self) -> tuple[str, ...]: ...


class PreventiveChecklist(MaintenanceChecklist):
    def items(self):
        return ("Limpeza", "Lubrificação", "Proteções", "Teste funcional")


class CorrectiveChecklist(MaintenanceChecklist):
    def items(self):
        return ("Confirmar sintoma", "Isolar causa", "Executar reparo", "Teste final")


class PreventiveRoute(MaintenanceRoute):
    def steps(self):
        return ("Preparar", "Inspecionar", "Testar", "Liberar")


class CorrectiveRoute(MaintenanceRoute):
    def steps(self):
        return ("Diagnosticar", "Reparar", "Validar", "Liberar")


class MaintenanceFamilyFactory(ABC):
    @abstractmethod
    def create_checklist(self) -> MaintenanceChecklist: ...

    @abstractmethod
    def create_route(self) -> MaintenanceRoute: ...


class PreventiveMaintenanceFactory(MaintenanceFamilyFactory):
    def create_checklist(self):
        return PreventiveChecklist()

    def create_route(self):
        return PreventiveRoute()


class CorrectiveMaintenanceFactory(MaintenanceFamilyFactory):
    def create_checklist(self):
        return CorrectiveChecklist()

    def create_route(self):
        return CorrectiveRoute()


@dataclass(frozen=True)
class MaintenanceKit:
    checklist: tuple[str, ...]
    route: tuple[str, ...]


class MaintenancePlanningService:
    """Cliente do Abstract Factory, sem conhecer os produtos concretos."""

    def __init__(self, factory: MaintenanceFamilyFactory):
        self.factory = factory

    def prepare(self):
        checklist = self.factory.create_checklist()
        route = self.factory.create_route()
        return MaintenanceKit(checklist.items(), route.steps())


class MaintenanceKitFactory:
    """Fachada que escolhe a família e delega sua criação ao Abstract Factory."""

    @staticmethod
    def create(kind):
        factory = PreventiveMaintenanceFactory() if kind == ServiceOrder.Type.PREVENTIVE else CorrectiveMaintenanceFactory()
        return MaintenancePlanningService(factory).prepare()


class Prototype(ABC):
    """Contrato do padrão Prototype: o objeto sabe se clonar sem expor como é construído."""

    @abstractmethod
    def clone(self, **overrides): ...


class MaintenancePlanPrototype(Prototype):
    """Usa um plano existente como protótipo para outros equipamentos.

    O clone herda modalidade, periodicidade, criticidade e checklist (copiados em profundidade),
    mas nasce sem histórico: sem última manutenção, sem horas de referência e com nova data de
    vencimento calculada a partir do próprio intervalo.
    """

    INHERITED = (
        "name", "maintenance_type", "interval_days", "usage_limit", "advance_notice_days",
        "advance_notice_usage_hours", "criticality", "checklist", "active",
    )

    def __init__(self, plan):
        self._plan = plan

    def clone(self, **overrides):
        from copy import deepcopy

        from .models import MaintenancePlan

        data = {field: deepcopy(getattr(self._plan, field)) for field in self.INHERITED}
        data.update(overrides)
        if data.get("equipment") is None:
            raise ValueError("O clone precisa de um equipamento de destino.")
        return MaintenancePlan(**data)  # não persiste: quem chama decide quando salvar
