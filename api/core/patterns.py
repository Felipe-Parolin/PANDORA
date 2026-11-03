from dataclasses import dataclass, field
from threading import Lock
from typing import ClassVar

from django.conf import settings


@dataclass(frozen=True)
class AISettings:
    """Singleton imutável com a configuração do assistente de IA.

    Não guarda dados de usuários. A chave de API fica fora do ``repr`` para não
    vazar em logs ou tracebacks.
    """

    model: str = "llama-3.3-70b-versatile"
    result_limit: int = 5
    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.groq.com/openai/v1"
    transcription_model: str = "whisper-large-v3-turbo"
    timeout_seconds: float = 30.0
    max_context_chars: int = 12000
    max_audio_bytes: int = 10 * 1024 * 1024
    enabled: bool = True
    _instance: ClassVar["AISettings | None"] = None
    _lock: ClassVar[Lock] = Lock()

    @property
    def configured(self) -> bool:
        """Há chave e o recurso não foi desligado pelo administrador."""
        return bool(self.enabled and self.api_key)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(
                        model=getattr(settings, "AI_MODEL", "llama-3.3-70b-versatile"),
                        result_limit=getattr(settings, "AI_RESULT_LIMIT", 5),
                        api_key=getattr(settings, "GROQ_API_KEY", ""),
                        base_url=getattr(settings, "AI_BASE_URL", "https://api.groq.com/openai/v1"),
                        transcription_model=getattr(settings, "AI_TRANSCRIPTION_MODEL", "whisper-large-v3-turbo"),
                        timeout_seconds=getattr(settings, "AI_TIMEOUT_SECONDS", 30.0),
                        max_context_chars=getattr(settings, "AI_MAX_CONTEXT_CHARS", 12000),
                        max_audio_bytes=getattr(settings, "AI_MAX_AUDIO_BYTES", 10 * 1024 * 1024),
                        enabled=getattr(settings, "AI_ENABLED", True),
                    )
        return cls._instance

    @classmethod
    def instance(cls):
        return cls.get_instance()

    @classmethod
    def reset(cls):
        """Descarta a instância (uso restrito a testes e a recarga de configuração)."""
        with cls._lock:
            cls._instance = None


class AIService:
    """Consumidor do Singleton; não armazena dados mutáveis de usuários."""

    def __init__(self, configuration=None):
        self.configuration = configuration or AISettings.get_instance()

    def get_configuration(self):
        return self.configuration
