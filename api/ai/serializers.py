from rest_framework import serializers

from assets.models import Equipment
from maintenance.models import ServiceOrder

from .models import AIConsultation, AIDecision, AIRecommendation, UnfulfilledDemand


class _InputSource(serializers.Serializer):
    input_source = serializers.ChoiceField(choices=("TEXT", "VOICE"), default="TEXT")
    transcription_confirmed = serializers.BooleanField(default=False)


class SearchInputSerializer(_InputSource):
    query = serializers.CharField(min_length=3, max_length=2000)
    equipment = serializers.PrimaryKeyRelatedField(queryset=Equipment.objects.all(), required=False, allow_null=True)
    service_order = serializers.PrimaryKeyRelatedField(queryset=ServiceOrder.objects.all(), required=False, allow_null=True)


class DiagnoseInputSerializer(_InputSource):
    symptoms = serializers.CharField(min_length=3, max_length=2000, required=False, allow_blank=True)
    equipment = serializers.PrimaryKeyRelatedField(queryset=Equipment.objects.all(), required=False, allow_null=True)
    service_order = serializers.PrimaryKeyRelatedField(queryset=ServiceOrder.objects.select_related("equipment__category"), required=False, allow_null=True)

    def validate(self, attrs):
        order, equipment = attrs.get("service_order"), attrs.get("equipment")
        if order and equipment and order.equipment_id != equipment.pk:
            raise serializers.ValidationError("O equipamento informado não corresponde à OS.")
        attrs["equipment"] = equipment or (order.equipment if order else None)
        attrs["symptoms"] = (attrs.get("symptoms") or (order.symptoms if order else "")).strip()
        if len(attrs["symptoms"]) < 3:
            raise serializers.ValidationError({"symptoms": "Descreva o problema ou informe uma OS."})
        if attrs["equipment"] is None:
            raise serializers.ValidationError({"equipment": "Selecione o equipamento para consultar a IA."})
        return attrs


class AskInputSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=3, max_length=1000)
    equipment = serializers.PrimaryKeyRelatedField(queryset=Equipment.objects.all(), required=False, allow_null=True)


class ExtractInputSerializer(_InputSource):
    text = serializers.CharField(min_length=3, max_length=4000)
    equipment = serializers.PrimaryKeyRelatedField(queryset=Equipment.objects.select_related("category"), required=False, allow_null=True)
    maintenance_type = serializers.ChoiceField(choices=("CORRECTIVE", "PREVENTIVE"), required=False, allow_blank=True, default="")


class TranscribeInputSerializer(serializers.Serializer):
    audio = serializers.FileField()


class DecisionInputSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=AIDecision.Decision.choices)
    reason = serializers.CharField(max_length=2000)
    final_text = serializers.CharField(max_length=3000, required=False, allow_blank=True, default="")
    apply_to_order = serializers.BooleanField(default=False)
    final_tests = serializers.CharField(max_length=3000, required=False, allow_blank=True, default="")
    parts_used = serializers.CharField(max_length=3000, required=False, allow_blank=True, default="")


class ReportPeriodSerializer(serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs.get("start") and attrs.get("end") and attrs["start"] > attrs["end"]:
            raise serializers.ValidationError("A data inicial deve ser anterior à final.")
        if attrs.get("start") and attrs.get("end") and (attrs["end"] - attrs["start"]).days > 366:
            raise serializers.ValidationError("O período máximo do relatório é de 366 dias.")
        return attrs


class ReindexInputSerializer(serializers.Serializer):
    equipment = serializers.PrimaryKeyRelatedField(queryset=Equipment.objects.all(), required=False)
    media = serializers.IntegerField(required=False)


class AIDecisionSerializer(serializers.ModelSerializer):
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default="")
    decision_label = serializers.CharField(source="get_decision_display", read_only=True)

    class Meta:
        model = AIDecision
        fields = ("id", "decision", "decision_label", "reason", "final_text", "applied_to_order", "decided_by", "decided_by_name", "created_at")


class AIConsultationSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True, default="")
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    equipment_name = serializers.CharField(source="equipment.name", read_only=True, default="")
    order_number = serializers.CharField(source="service_order.number", read_only=True, default="")
    decisions = AIDecisionSerializer(many=True, read_only=True)

    class Meta:
        model = AIConsultation
        fields = ("id", "kind", "kind_label", "input_source", "transcription_confirmed", "status", "status_label", "model", "latency_ms",
                  "equipment", "equipment_name", "service_order", "order_number", "user", "user_name", "query_text", "response",
                  "decisions", "created_at")
        read_only_fields = fields


class AIRecommendationSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="equipment.name", read_only=True, default="")
    equipment_code = serializers.CharField(source="equipment.internal_code", read_only=True, default="")
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    service_order_number = serializers.CharField(source="service_order.number", read_only=True, default="")
    generated_by_name = serializers.CharField(source="generated_by.full_name", read_only=True, default="")
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default="")
    closed_by_name = serializers.CharField(source="closed_by.full_name", read_only=True, default="")
    reason = serializers.SerializerMethodField()

    def get_reason(self, obj):
        """Motivo pelo qual a IA sugeriu a compra (também reconstruído para registros antigos)."""
        if obj.kind != AIRecommendation.Kind.EQUIPMENT_PURCHASE:
            return ""
        payload = obj.suggested_payload or {}
        if payload.get("reason"):
            return payload["reason"]
        if "maintenance_count" not in payload and "demand_count" not in payload:
            return ""
        from .recommendations import purchase_reason
        return purchase_reason(payload.get("demand_count", 0), payload.get("maintenance_count", 0),
                               payload.get("downtime_days", 0), payload.get("lookback_days", 180), obj.estimated_recoverable_revenue)

    class Meta:
        model = AIRecommendation
        fields = "__all__"


class UnfulfilledDemandSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="equipment.name", read_only=True, default="")
    equipment_code = serializers.CharField(source="equipment.internal_code", read_only=True, default="")
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    recorded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    # Permite informar uma categoria nova ao registrar um pedido de item que a empresa ainda não possui.
    new_category_name = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=100)

    class Meta:
        model = UnfulfilledDemand
        fields = "__all__"
        read_only_fields = ("id", "recorded_by", "created_at", "equipment_name", "equipment_code", "category_name", "customer_name", "reason_label")

    def validate_requested_days(self, value):
        if value < 1 or value > 365:
            raise serializers.ValidationError("Informe entre 1 e 365 dias de locação solicitada.")
        return value

    def validate_quantity(self, value):
        if value < 1 or value > 100:
            raise serializers.ValidationError("Informe entre 1 e 100 unidades.")
        return value

    def validate_expected_daily_rate(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("A diária estimada deve ser maior que zero.")
        return value

    def validate_requested_at(self, value):
        from django.utils import timezone
        if value > timezone.localdate():
            raise serializers.ValidationError("A data da solicitação não pode estar no futuro.")
        return value

    def validate(self, attrs):
        equipment = attrs.get("equipment")
        category = attrs.get("category")
        new_name = (attrs.get("new_category_name") or "").strip()
        item = (attrs.get("requested_item") or "").strip()
        if not (equipment or category or new_name or item):
            raise serializers.ValidationError("Informe o equipamento, a categoria ou o nome do item solicitado pelo cliente.")
        attrs["requested_item"] = item
        return attrs

    def create(self, validated_data):
        from assets.models import EquipmentCategory
        validated_data["recorded_by"] = self.context["request"].user
        new_name = (validated_data.pop("new_category_name", "") or "").strip()
        equipment = validated_data.get("equipment")
        if equipment is not None:
            validated_data["category"] = equipment.category
            if validated_data.get("expected_daily_rate") is None:
                validated_data["expected_daily_rate"] = equipment.daily_rate
        elif validated_data.get("category") is None and new_name:
            validated_data["category"], _ = EquipmentCategory.objects.get_or_create(name=new_name)
        category = validated_data.get("category")
        if validated_data.get("expected_daily_rate") is None and category is not None and category.default_daily_rate:
            validated_data["expected_daily_rate"] = category.default_daily_rate
        return super().create(validated_data)
