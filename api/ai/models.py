from django.conf import settings
from django.db import models


class ManualIndex(models.Model):
    """Estado da indexação textual de um manual/documento PDF."""

    class Status(models.TextChoices):
        INDEXED = "INDEXED", "Indexado"
        NO_TEXT = "NO_TEXT", "Sem texto extraível"
        ERROR = "ERROR", "Falha na leitura"

    media = models.OneToOneField("assets.MediaAsset", on_delete=models.CASCADE, related_name="ai_index")
    status = models.CharField(max_length=12, choices=Status.choices)
    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=255, blank=True)
    indexed_at = models.DateTimeField(auto_now=True)


class ManualChunk(models.Model):
    media = models.ForeignKey("assets.MediaAsset", on_delete=models.CASCADE, related_name="ai_chunks")
    position = models.PositiveIntegerField()
    page = models.PositiveIntegerField(default=1)
    text = models.TextField()

    class Meta:
        ordering = ("media_id", "position")
        constraints = [models.UniqueConstraint(fields=("media", "position"), name="unique_manual_chunk_position")]


class AIConsultation(models.Model):
    """Registro auditável de cada consulta feita à IA (RF37).

    O texto da consulta é gravado já anonimizado e nenhum áudio é guardado.
    """

    class Kind(models.TextChoices):
        DIAGNOSIS = "DIAGNOSIS", "Hipóteses de diagnóstico"
        MANUAL_QA = "MANUAL_QA", "Pergunta aos manuais"
        SEARCH = "SEARCH", "Busca de casos semelhantes"
        TRANSCRIPTION = "TRANSCRIPTION", "Transcrição de voz"
        REPORT_EXTRACTION = "REPORT_EXTRACTION", "Extração de relato"
        REPORT_SUMMARY = "REPORT_SUMMARY", "Resumo de relatório"

    class Source(models.TextChoices):
        TEXT = "TEXT", "Texto"
        VOICE = "VOICE", "Voz"

    class Status(models.TextChoices):
        OK = "OK", "Respondida pela IA"
        DEGRADED = "DEGRADED", "IA indisponível (apenas busca local)"
        ERROR = "ERROR", "Erro"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_consultations")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    input_source = models.CharField(max_length=8, choices=Source.choices, default=Source.TEXT)
    transcription_confirmed = models.BooleanField(default=False)
    equipment = models.ForeignKey("assets.Equipment", on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_consultations")
    service_order = models.ForeignKey("maintenance.ServiceOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_consultations")
    query_text = models.TextField(blank=True)
    response = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OK)
    model = models.CharField(max_length=80, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")


class AIDecision(models.Model):
    """Decisão humana sobre uma recomendação da IA (RF33/RF34/RN7/RN8)."""

    class Decision(models.TextChoices):
        ACCEPTED = "ACCEPTED", "Aceita"
        CORRECTED = "CORRECTED", "Corrigida"
        REJECTED = "REJECTED", "Rejeitada"

    consultation = models.ForeignKey(AIConsultation, on_delete=models.CASCADE, related_name="decisions")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ai_decisions")
    decision = models.CharField(max_length=10, choices=Decision.choices)
    reason = models.TextField()
    final_text = models.TextField(blank=True)
    applied_to_order = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")


class AIRecommendation(models.Model):
    """Recomendação operacional estruturada, revisável e auditável."""

    class Kind(models.TextChoices):
        PREVENTIVE_MAINTENANCE = "PREVENTIVE_MAINTENANCE", "Manutenção preventiva"
        EQUIPMENT_PURCHASE = "EQUIPMENT_PURCHASE", "Aquisição de equipamento"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        ACCEPTED = "ACCEPTED", "Aceita"
        REJECTED = "REJECTED", "Rejeitada"
        POSTPONED = "POSTPONED", "Adiada"
        PURCHASED = "PURCHASED", "Comprada"
        DISCARDED = "DISCARDED", "Descartada"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    equipment = models.ForeignKey("assets.Equipment", on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_recommendations")
    title = models.CharField(max_length=200)
    summary = models.TextField()
    rationale = models.TextField(blank=True)
    priority = models.CharField(max_length=12, default="MEDIUM")
    evidence = models.JSONField(default=list, blank=True)
    suggested_payload = models.JSONField(default=dict, blank=True)
    estimated_recoverable_revenue = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estimated_purchase_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estimated_monthly_benefit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    payback_months = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="generated_ai_recommendations")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="decided_ai_recommendations")
    decision_reason = models.TextField(blank=True)
    service_order = models.ForeignKey("maintenance.ServiceOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_recommendations")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    # Encerramento de uma aquisição aceita (comprada ou descartada pelo gestor).
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="closed_ai_recommendations")
    closure_note = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("status", "-created_at")
        indexes = [models.Index(fields=("kind", "status"), name="ai_airecomm_kind_5a1c4f_idx"), models.Index(fields=("equipment", "created_at"), name="ai_airecomm_equipme_0a9d4b_idx")]


class UnfulfilledDemand(models.Model):
    """Registra demanda real não atendida; não infere perda de receita só pela indisponibilidade."""

    # Pedido de um equipamento cadastrado OU de uma categoria/item que a empresa ainda não possui.
    equipment = models.ForeignKey("assets.Equipment", on_delete=models.PROTECT, null=True, blank=True, related_name="unfulfilled_demands")
    category = models.ForeignKey("assets.EquipmentCategory", on_delete=models.PROTECT, null=True, blank=True, related_name="unfulfilled_demands")
    requested_item = models.CharField(max_length=160, blank=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="unfulfilled_demands")
    quantity = models.PositiveSmallIntegerField(default=1)
    requested_days = models.PositiveIntegerField(default=1)
    expected_daily_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    requested_at = models.DateField()
    reason = models.CharField(max_length=24, choices=(
        ("UNAVAILABLE", "Sem unidade disponível"),
        ("MAINTENANCE", "Equipamento em manutenção"),
        ("FLEET_CAPACITY", "Capacidade insuficiente da frota"),
        ("OTHER", "Outro motivo"),
    ), default="UNAVAILABLE")
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="recorded_unfulfilled_demands")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-requested_at", "-id")
