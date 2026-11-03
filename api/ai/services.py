"""Fachada do assistente de IA (padrão Facade).

Orquestra permissões, anonimização, recuperação, chamada ao LLM, validação e auditoria. A
locação e a manutenção nunca dependem deste módulo: se o LLM falhar, a busca local continua.
"""
import logging
import re
import time
from datetime import date

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from assets.models import Equipment
from core.models import AuditLog
from core.patterns import AISettings
from customers.models import Customer
from maintenance.models import ServiceOrder
from maintenance.patterns import AudioReport, ReportProcessorFactory

from . import prompts
from .models import AIConsultation, AIDecision
from .providers import LLMError, get_llm_provider
from .retrieval import BM25Retriever, KnowledgeBase, build_source
from .risk import RiskAnalyzer
from .text import redact, tokenize, truncate

logger = logging.getLogger(__name__)

ALLOWED_AUDIO_PREFIXES = ("audio/", "video/webm", "video/mp4", "application/ogg")
TERMINAL_ORDER_STATUSES = (ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED)


class AIUnavailable(APIException):
    status_code = 503
    default_code = "ai_unavailable"
    default_detail = "O assistente de IA está indisponível no momento. Locações e manutenção seguem normalmente."


class AIAssistantFacade:
    def __init__(self, user, *, provider=None, retriever=None, analyzer=None, config=None):
        self.user = user
        self.config = config or AISettings.get_instance()
        self.provider = provider or get_llm_provider()
        self.retriever = retriever or BM25Retriever()
        self.analyzer = analyzer or RiskAnalyzer()
        self.kb = KnowledgeBase(user)
        self._customer_names = None

    # ------------------------------------------------------------------ infraestrutura

    def status(self) -> dict:
        return {
            "configured": self.config.configured, "available": self.provider.available, "model": self.config.model,
            "transcription_model": self.config.transcription_model,
            "can_read_orders": self.kb.can_read_orders(), "can_read_manuals": self.kb.can_read_manuals(),
        }

    def _redact(self, text: str) -> str:
        if self._customer_names is None:
            self._customer_names = list(Customer.objects.values_list("name", flat=True))
        return redact(text, self._customer_names)

    def _record(self, kind, *, equipment=None, order=None, query="", response=None, status=AIConsultation.Status.OK,
                started=None, input_source="TEXT", confirmed=False) -> AIConsultation:
        consultation = AIConsultation.objects.create(
            user=self.user, kind=kind, equipment=equipment, service_order=order, query_text=truncate(query, 2000),
            response=response or {}, status=status, model=self.config.model if status == AIConsultation.Status.OK else "",
            latency_ms=int((time.monotonic() - started) * 1000) if started else 0,
            input_source=input_source, transcription_confirmed=confirmed,
        )
        AuditLog.objects.create(
            user=self.user, entity="AIConsultation", record_id=str(consultation.pk), action=f"CONSULT_{kind}",
            data={"equipment": equipment.pk if equipment else None, "service_order": order.pk if order else None,
                  "status": status, "source": input_source},
        )
        return consultation

    def _retrieve(self, query, equipment, order=None):
        limit = self.config.result_limit
        orders = self.retriever.search(query, self.kb.order_documents(equipment, exclude_order=order), limit)
        manuals = self.retriever.search(query, self.kb.manual_documents(equipment), limit)
        sources = [build_source(f"S{i}", hit) for i, hit in enumerate([*orders, *manuals], start=1)]
        return sources

    @staticmethod
    def _search_query(text, equipment):
        return f"{text} {equipment.name} {equipment.model}" if equipment else text

    def _call(self, system, user_prompt, max_tokens=1200):
        if not self.provider.available:
            raise AIUnavailable()
        try:
            return self.provider.complete_json(system, user_prompt, max_tokens=max_tokens)
        except LLMError as exc:
            logger.info("IA indisponível ou resposta inválida: %s", type(exc).__name__)
            raise AIUnavailable() from exc

    # ------------------------------------------------------------------ consultas

    def search(self, query, equipment=None, order=None, input_source="TEXT"):
        """Busca de casos semelhantes e trechos de manuais, sem LLM (RF31)."""
        started = time.monotonic()
        safe_query = self._redact(query)
        sources = self._retrieve(self._search_query(safe_query, equipment), equipment, order)
        result = {"ai_available": False, "sources": sources, "query": safe_query}
        consultation = self._record(AIConsultation.Kind.SEARCH, equipment=equipment, order=order, query=safe_query,
                                    response=result, started=started, input_source=input_source)
        return {**result, "consultation_id": consultation.pk}

    def diagnose(self, symptoms, equipment, order=None, input_source="TEXT", confirmed=False):
        started = time.monotonic()
        if order is not None and order.status in TERMINAL_ORDER_STATUSES:
            raise ValidationError({"service_order": "OS encerrada: a consulta à IA está travada. Veja a resposta adotada no histórico da OS."})
        if input_source == "VOICE" and not confirmed:
            raise ValidationError({"transcription_confirmed": "Confirme a transcrição antes de consultar a IA."})
        safe_symptoms = self._redact(symptoms)
        notes = self._redact(order.diagnosis) if order is not None and order.diagnosis else ""
        sources = self._retrieve(self._search_query(safe_symptoms, equipment), equipment, order)
        assessment = self.analyzer.assess(equipment) if equipment else None
        recurrence = assessment.__dict__ if assessment else None
        analysis, notice, status = None, None, AIConsultation.Status.OK
        try:
            raw = self._call(
                prompts.diagnosis_system(),
                prompts.diagnosis_user(equipment, safe_symptoms, notes, assessment, sources, self.config.max_context_chars),
            )
            analysis = prompts.normalize_diagnosis(raw, {s["id"] for s in sources}, bool(sources))
        except AIUnavailable as exc:
            status = AIConsultation.Status.DEGRADED
            notice = "A IA não respondeu agora. Exibindo apenas casos semelhantes e trechos de manuais encontrados nos registros."
            logger.info("Consulta degradada: %s", exc.default_code)
        result = {
            "ai_available": status == AIConsultation.Status.OK, "notice": notice, "analysis": analysis, "sources": sources,
            "recurrence": recurrence, "disclaimer": prompts.DISCLAIMER, "query": safe_symptoms,
        }
        consultation = self._record(AIConsultation.Kind.DIAGNOSIS, equipment=equipment, order=order, query=safe_symptoms,
                                    response=result, status=status, started=started, input_source=input_source, confirmed=confirmed)
        return {**result, "consultation_id": consultation.pk, "status": status}

    def ask(self, question, equipment=None):
        started = time.monotonic()
        safe_question = self._redact(question)
        sources = self._retrieve(self._search_query(safe_question, equipment), equipment)
        analysis, notice, status = None, None, AIConsultation.Status.OK
        if not sources:
            analysis = {"answer": "", "citations": [], "insufficient_data": True,
                        "limitations": "Não encontrei trechos de manuais ou casos autorizados relacionados a esta pergunta."}
        else:
            try:
                raw = self._call(prompts.qa_system(), prompts.qa_user(equipment, safe_question, sources, self.config.max_context_chars))
                analysis = prompts.normalize_qa(raw, {s["id"]: s for s in sources})
            except AIUnavailable:
                status = AIConsultation.Status.DEGRADED
                notice = "A IA não respondeu agora. Os trechos abaixo foram localizados nos registros autorizados."
        result = {"ai_available": status == AIConsultation.Status.OK, "notice": notice, "analysis": analysis, "sources": sources,
                  "disclaimer": prompts.DISCLAIMER, "query": safe_question}
        consultation = self._record(AIConsultation.Kind.MANUAL_QA, equipment=equipment, query=safe_question, response=result, status=status, started=started)
        return {**result, "consultation_id": consultation.pk, "status": status}

    # ------------------------------------------------------------------ registro por voz/texto (RF28)

    def transcribe(self, upload):
        started = time.monotonic()
        content_type = (upload.content_type or "").lower()
        if not content_type.startswith(ALLOWED_AUDIO_PREFIXES):
            raise ValidationError({"audio": "Formato de áudio não suportado."})
        if upload.size > self.config.max_audio_bytes:
            raise ValidationError({"audio": f"O áudio deve ter no máximo {self.config.max_audio_bytes // (1024 * 1024)} MB."})
        if upload.size == 0:
            raise ValidationError({"audio": "O áudio está vazio."})
        if not self.provider.available:
            raise AIUnavailable("A transcrição por voz está indisponível. Digite o relato.")
        audio = AudioReport(content=upload.read(), filename=upload.name or "relato.webm", content_type=content_type)
        try:
            text = ReportProcessorFactory.creator("audio").create_processor_with(self._transcribe).process(audio)
        except LLMError as exc:
            raise AIUnavailable("Não foi possível transcrever o áudio agora. Digite o relato.") from exc
        safe_text = self._redact(text)
        consultation = self._record(AIConsultation.Kind.TRANSCRIPTION, query=safe_text, response={"characters": len(text)},
                                    started=started, input_source="VOICE")
        return {"text": text, "consultation_id": consultation.pk}

    def _transcribe(self, audio, filename, content_type):
        vocabulary = ", ".join(Equipment.objects.values_list("name", flat=True).distinct()[:12])
        return self.provider.transcribe(audio, filename, content_type, prompt=f"Relato técnico de manutenção. Equipamentos: {vocabulary}.")

    def extract_report(self, text, input_source="TEXT", confirmed=False, equipment=None, maintenance_type=""):
        """Organiza/reformula o relato do chamado. Com equipamento escolhido, considera seus manuais e casos anteriores."""
        started = time.monotonic()
        if input_source == "VOICE" and not confirmed:
            raise ValidationError({"transcription_confirmed": "Confirme a transcrição antes de extrair os dados."})
        cleaned = ReportProcessorFactory.process("text", text)
        safe_text = self._redact(cleaned)
        sources = self._retrieve(self._search_query(safe_text, equipment), equipment) if equipment is not None else []
        extraction, notice, status = None, None, AIConsultation.Status.OK
        try:
            extraction = prompts.normalize_extraction(self._call(
                prompts.extract_system(bool(sources)),
                prompts.extract_user(safe_text, equipment, maintenance_type, sources, self.config.max_context_chars), 900,
            ))
        except AIUnavailable:
            status = AIConsultation.Status.DEGRADED
            notice = "A IA não respondeu. Revise o texto e preencha os campos manualmente."
            extraction = {"symptoms": cleaned, "equipment_hint": "", "model": "", "location": "", "urgency_hint": "", "additional_info": [], "missing_info": []}
        extraction["symptoms"] = extraction["symptoms"] or cleaned
        candidates = self.match_equipment(" ".join((extraction["equipment_hint"], extraction["model"], cleaned)))
        result = {"ai_available": status == AIConsultation.Status.OK, "notice": notice, "extraction": extraction, "equipment_candidates": candidates,
                  "sources": sources}
        consultation = self._record(AIConsultation.Kind.REPORT_EXTRACTION, equipment=equipment, query=safe_text, response=result, status=status,
                                    started=started, input_source=input_source, confirmed=confirmed)
        return {**result, "consultation_id": consultation.pk, "status": status}

    @staticmethod
    def match_equipment(text, limit=3):
        code = re.search(r"\b[A-Z]{2,4}-\d{2,5}\b", (text or "").upper())
        wanted = set(tokenize(text))
        ranked = []
        for item in Equipment.objects.exclude(status=Equipment.Status.INACTIVE).select_related("category"):
            if code and item.internal_code.upper() == code.group(0):
                ranked.append((10.0, item))
                continue
            terms = set(tokenize(f"{item.name} {item.brand} {item.model} {item.category.name}"))
            overlap = wanted & terms
            if overlap:
                ranked.append((len(overlap) / (len(terms) ** 0.5), item))
        ranked.sort(key=lambda pair: -pair[0])
        return [{"id": e.pk, "internal_code": e.internal_code, "name": e.name, "model": e.model, "score": round(score, 2)} for score, e in ranked[:limit]]

    # ------------------------------------------------------------------ relatórios

    def summarize_report(self, report: dict):
        started = time.monotonic()
        payload = {k: report[k] for k in ("period", "availability", "rentals", "maintenance", "recurrence")}
        payload["rentals"] = {**payload["rentals"], "late_returns": len(report["rentals"]["late_returns"]), "late_deliveries": len(report["rentals"]["late_deliveries"])}
        payload["maintenance"] = {**payload["maintenance"], "late_orders": len(report["maintenance"]["late_orders"]), "overdue_plans": len(report["maintenance"]["overdue_plans"])}
        payload["availability"] = {k: v for k, v in payload["availability"].items() if k != "blocked"}
        status, summary, notice = AIConsultation.Status.OK, None, None
        try:
            summary = prompts.normalize_report_summary(self._call(prompts.report_system(), prompts.dumps(payload), 900))
        except AIUnavailable:
            status, notice = AIConsultation.Status.DEGRADED, "A IA não respondeu. Os números do relatório continuam disponíveis."
        result = {"ai_available": status == AIConsultation.Status.OK, "notice": notice, "summary": summary, "disclaimer": prompts.DISCLAIMER}
        consultation = self._record(AIConsultation.Kind.REPORT_SUMMARY, response=result, status=status, started=started)
        return {**result, "consultation_id": consultation.pk}

    # ------------------------------------------------------------------ decisão humana (RF33/RF34, RN7/RN8)

    @transaction.atomic
    def decide(self, consultation, decision, reason, final_text="", apply_to_order=False, final_tests="", parts_used=""):
        if consultation.user_id != self.user.pk and not self.user.has_acl("ai.audit"):
            raise PermissionDenied("Esta consulta pertence a outro usuário.")
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise ValidationError({"reason": "Informe o motivo da sua decisão."})
        final_text = (final_text or "").strip()
        if decision == AIDecision.Decision.CORRECTED and not final_text:
            raise ValidationError({"final_text": "Descreva a correção feita à recomendação da IA."})
        applied = False
        order = consultation.service_order
        if apply_to_order:
            if decision == AIDecision.Decision.REJECTED:
                raise ValidationError({"apply_to_order": "Uma recomendação rejeitada não pode ser aplicada à OS."})
            if order is None:
                raise ValidationError({"apply_to_order": "Esta consulta não está vinculada a uma OS."})
            if not self.user.has_acl("maintenance.manage"):
                raise PermissionDenied("Seu grupo não pode alterar o diagnóstico da OS.")
            if order.status in TERMINAL_ORDER_STATUSES:
                raise ValidationError({"apply_to_order": "A OS já está encerrada para alterações."})
            if not final_text:
                raise ValidationError({"final_text": "Informe o texto que será registrado no diagnóstico."})
            stamp = f"[Apoio de IA validado por {self.user.full_name or self.user.email} em {timezone.localdate():%d/%m/%Y}]"
            order.diagnosis = f"{order.diagnosis.rstrip()}\n\n{stamp} {final_text}".strip()
            fields = ["diagnosis"]
            for name, value in (("final_tests", final_tests), ("parts_used", parts_used)):
                value = (value or "").strip()
                if value:
                    current = getattr(order, name).rstrip()
                    setattr(order, name, f"{current}\n{value}".strip() if current else value)
                    fields.append(name)
            order.save(update_fields=tuple(fields))
            applied = True
        record = AIDecision.objects.create(consultation=consultation, decided_by=self.user, decision=decision, reason=reason,
                                           final_text=final_text, applied_to_order=applied)
        AuditLog.objects.create(
            user=self.user, entity="AIConsultation", record_id=str(consultation.pk), action=f"DECISION_{decision}",
            data={"decision_id": record.pk, "service_order": order.pk if order else None, "applied_to_order": applied, "reason": truncate(reason, 500)},
        )
        return record
