"""Acesso ao LLM: Adapter para a API compatível com OpenAI da Groq + Circuit Breaker."""
import json
import logging
import time
from abc import ABC, abstractmethod
from threading import Lock

import requests

from core.patterns import AISettings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Falha ao interpretar a resposta do modelo."""


class LLMUnavailable(LLMError):
    """Serviço indisponível, sem chave configurada ou circuito aberto."""


class LLMProvider(ABC):
    """Contrato que o restante do sistema conhece; a Groq é apenas uma implementação."""

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def complete_json(self, system: str, user: str, *, max_tokens: int = 1200, temperature: float = 0.2) -> dict: ...

    @abstractmethod
    def transcribe(self, audio: bytes, filename: str, content_type: str, *, language: str = "pt", prompt: str = "") -> str: ...


class CircuitBreaker:
    """Evita insistir em um serviço fora do ar e preserva a latência da operação (RNF6)."""

    def __init__(self, failure_threshold=3, cooldown_seconds=60, clock=time.monotonic):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at = None
        self._lock = Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if self._clock() - self._opened_at >= self.cooldown_seconds:
                self._opened_at, self._failures = None, 0  # meio-aberto: permite nova tentativa
                return False
            return True

    def success(self):
        with self._lock:
            self._failures, self._opened_at = 0, None

    def failure(self):
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = self._clock()


class GroqProvider(LLMProvider):
    RETRYABLE = {429, 500, 502, 503, 504}

    def __init__(self, config=None, session=None, breaker=None):
        self.config = config or AISettings.get_instance()
        self.session = session or requests.Session()
        from django.conf import settings
        self.breaker = breaker or CircuitBreaker(
            getattr(settings, "AI_BREAKER_FAILURES", 3), getattr(settings, "AI_BREAKER_COOLDOWN_SECONDS", 60)
        )

    @property
    def available(self) -> bool:
        return self.config.configured and not self.breaker.is_open

    @staticmethod
    def _error_detail(response) -> str:
        try:
            error = response.json().get("error", {})
            return str(error.get("message") or error.get("code") or "sem detalhe")[:300]
        except (ValueError, AttributeError):
            return "sem detalhe"

    def _headers(self):
        return {"Authorization": f"Bearer {self.config.api_key}"}

    def _post(self, path, **kwargs):
        if not self.config.configured:
            raise LLMUnavailable("O assistente de IA não está configurado.")
        if self.breaker.is_open:
            raise LLMUnavailable("O serviço de IA está temporariamente indisponível.")
        last_error = None
        for attempt in range(2):
            try:
                response = self.session.post(
                    f"{self.config.base_url}{path}", headers=self._headers(), timeout=self.config.timeout_seconds, **kwargs
                )
            except requests.RequestException as exc:
                last_error = exc
            else:
                if response.status_code < 400:
                    self.breaker.success()
                    return response
                if response.status_code in (401, 403):
                    # Credencial inválida não é falha transitória: não insiste nem conta como instabilidade.
                    logger.error("Groq recusou a credencial (HTTP %s).", response.status_code)
                    raise LLMUnavailable("A chave de API da IA foi recusada.")
                detail = self._error_detail(response)
                last_error = LLMError(f"HTTP {response.status_code}: {detail}")
                if response.status_code not in self.RETRYABLE:
                    # Erro de requisição (modelo inválido, payload recusado...): não é instabilidade do serviço.
                    logger.error("Groq recusou a requisição: %s", last_error)
                    raise LLMUnavailable(f"A Groq recusou a requisição ({detail}).")
            if attempt == 0:
                time.sleep(0.6)
        self.breaker.failure()
        logger.warning("Falha ao consultar a Groq: %s", last_error)
        raise LLMUnavailable("Não foi possível consultar o serviço de IA agora.")

    def complete_json(self, system, user, *, max_tokens=1200, temperature=0.2):
        payload = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if "gpt-oss" in self.config.model.lower():
            # Modelo de raciocínio: os tokens de "pensamento" contam no limite, então reduzimos o esforço e ampliamos o espaço.
            payload["reasoning_effort"] = "low"
            payload["max_tokens"] = max_tokens + 2000
        response = self._post("/chat/completions", json=payload)
        try:
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("Resposta do modelo em formato inesperado.") from exc
        if not isinstance(data, dict):
            raise LLMError("Resposta do modelo em formato inesperado.")
        return data

    def transcribe(self, audio, filename, content_type, *, language="pt", prompt=""):
        data = {"model": self.config.transcription_model, "language": language, "response_format": "json", "temperature": "0"}
        if prompt:
            data["prompt"] = prompt[:400]
        response = self._post("/audio/transcriptions", data=data, files={"file": (filename, audio, content_type)})
        try:
            return str(response.json().get("text", "")).strip()
        except ValueError as exc:
            raise LLMError("Resposta de transcrição em formato inesperado.") from exc


_provider: LLMProvider | None = None
_provider_lock = Lock()


def get_llm_provider() -> LLMProvider:
    """Instância única do adaptador, para que o circuit breaker seja compartilhado."""
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:
                _provider = GroqProvider()
    return _provider


def reset_llm_provider():
    global _provider
    with _provider_lock:
        _provider = None