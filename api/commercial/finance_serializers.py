from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from .models import Payment, Receivable
from .receivables import charges


class ReceivableSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    quote_number = serializers.CharField(source="quote.number", read_only=True, default="")
    charges = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()

    class Meta:
        model = Receivable
        fields = ("id", "number", "customer", "customer_name", "quote", "quote_number", "description", "issue_date", "due_date", "amount", "monthly_interest_rate", "grace_days", "status", "charges", "payment", "created_at", "updated_at")
        read_only_fields = ("quote", "status", "created_at", "updated_at")
        extra_kwargs = {
            "amount": {"min_value": Decimal("0.01")},
            "monthly_interest_rate": {"min_value": Decimal("0"), "max_value": Decimal("100")},
            "grace_days": {"max_value": 365},
        }

    def get_charges(self, obj):
        if obj.status == Receivable.Status.PAID:
            return next((item for item in obj.allocation.payment.snapshot["items"] if item["id"] == obj.pk), None)
        return charges(obj, timezone.localdate())

    def get_payment(self, obj):
        if obj.status != Receivable.Status.PAID:
            return None
        payment = obj.allocation.payment
        return {"id": payment.pk, "number": payment.number, "payment_date": payment.payment_date}

    def validate(self, attrs):
        if self.instance:
            forbidden = set(self.initial_data) - {"description", "due_date", "monthly_interest_rate", "grace_days"}
            if forbidden:
                raise serializers.ValidationError("Somente descrição, vencimento e condições dos juros podem ser alterados; a emissão e o valor original são preservados.")
            if self.instance.status != Receivable.Status.OPEN:
                raise serializers.ValidationError("Contas baixadas são preservadas no histórico e não podem ser alteradas.")
        issue = attrs.get("issue_date", self.instance.issue_date if self.instance else timezone.localdate())
        due = attrs.get("due_date", self.instance.due_date if self.instance else issue)
        if "due_date" in attrs and due < issue:
            raise serializers.ValidationError({"due_date": "O vencimento deve ser igual ou posterior à emissão."})
        if issue > timezone.localdate():
            raise serializers.ValidationError({"issue_date": "A emissão não pode ser futura."})
        if not self.instance and not attrs["customer"].is_active:
            raise serializers.ValidationError({"customer": "Selecione um cliente ativo."})
        return attrs


class SettlementPreviewSerializer(serializers.Serializer):
    customer = serializers.IntegerField(min_value=1)
    receivable_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=500)
    payment_date = serializers.DateField()

    def validate_receivable_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Não repita contas na seleção.")
        return sorted(value)

    def validate_payment_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Registre apenas pagamentos já realizados.")
        return value


class SettlementSerializer(SettlementPreviewSerializer):
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    idempotency_key = serializers.UUIDField()
    calculation_token = serializers.CharField(min_length=64, max_length=64)
    expected_total = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal("0.01"))


class PaymentSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)

    class Meta:
        model = Payment
        fields = ("id", "number", "customer", "payment_date", "method", "principal", "interest", "total", "snapshot", "snapshot_hash", "created_at")
        read_only_fields = fields
