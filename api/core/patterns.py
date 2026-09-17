from dataclasses import dataclass
from threading import Lock
from typing import ClassVar
from django.conf import settings


@dataclass(frozen=True)
class AISettings:
    model: str
    result_limit: int
    _instance: ClassVar["AISettings | None"] = None
    _lock: ClassVar[Lock] = Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(
                        model=getattr(settings, "AI_MODEL", "llama-3.3-70b-versatile"),
                        result_limit=getattr(settings, "AI_RESULT_LIMIT", 5),
                    )
        return cls._instance

    @classmethod
    def instance(cls):
        return cls.get_instance()


class AIService:
    """Consumidor do Singleton; não armazena dados mutáveis de usuários."""

    def __init__(self, configuration=None):
        self.configuration = configuration or AISettings.get_instance()

    def get_configuration(self):
        return self.configuration
