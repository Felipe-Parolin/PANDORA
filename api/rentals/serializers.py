from django.db import transaction
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
import re
from rest_framework import serializers

from assets.models import Equipment
from maintenance.models import ServiceOrder
from logistics.serializers import TransportTaskSerializer
from logistics.services import ensure_transport_task
from logistics.models import TransportTask
from .models import RentalExtension, RentalInspection, RentalItem, RentalQuote
from .services import availability_reason, ensure_inspections, ensure_pre_rental_orders, refresh_equipment_status


class RentalItemSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    internal_code = serializers.CharField(source="equipment.internal_code", read_only=True)
    equipment_id = serializers.PrimaryKeyRelatedField(source="equipment", queryset=Equipment.objects.all(), write_only=True)

    class Meta:
        model = RentalItem
        fields = ("id", "equipment", "equipment_id", "equipment_name", "internal_code", "daily_rate", "quantity_days", "total", "condition_out")
        read_only_fields = ("equipment", "total")


class RentalInspectionSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    internal_code = serializers.CharField(source="equipment.internal_code", read_only=True)
    category_name = serializers.CharField(source="equipment.category.name", read_only=True)
    inspection_type_label = serializers.CharField(source="get_inspection_type_display", read_only=True)
    result_label = serializers.CharField(source="get_result_display", read_only=True)
    condition_label = serializers.CharField(source="get_condition_display", read_only=True)
    performed_by_name = serializers.CharField(source="performed_by.full_name", read_only=True)
    media_count = serializers.SerializerMethodField()

    class Meta:
        model = RentalInspection
        fields = "__all__"
        read_only_fields = ("quote", "equipment", "inspection_type", "performed_by", "performed_at", "created_at", "updated_at")

    def get_media_count(self, obj):
        return obj.media.count()

    def validate(self, attrs):
        if self.instance:
            expected_status = (
                RentalQuote.Status.APPROVED
                if self.instance.inspection_type == RentalInspection.Type.PRE_RENTAL
                else RentalQuote.Status.RETURNED
            )
            if self.instance.quote.status != expected_status:
                raise serializers.ValidationError("Esta inspeção não está disponível na etapa atual da locação.")
        result = attrs.get("result", getattr(self.instance, "result", RentalInspection.Result.PENDING))
        checklist = attrs.get("checklist", getattr(self.instance, "checklist", []))
        condition = attrs.get("condition", getattr(self.instance, "condition", RentalInspection.Condition.GOOD))
        critical = attrs.get("critical_impediment", getattr(self.instance, "critical_impediment", False))
        if result != RentalInspection.Result.PENDING:
            pending = [item for item in checklist if item.get("status") not in {"OK", "WARNING", "FAIL", "NA"}]
            if pending:
                raise serializers.ValidationError({"checklist": "Conclua todos os itens antes de finalizar a inspeção."})
        if critical or condition == RentalInspection.Condition.CRITICAL or any(item.get("status") == "FAIL" for item in checklist):
            attrs["critical_impediment"] = True
            attrs["result"] = RentalInspection.Result.BLOCKED
        return attrs

    def update(self, instance, validated_data):
        result = validated_data.get("result", instance.result)
        actor = self.context["request"].user
        if result != RentalInspection.Result.PENDING:
            validated_data["performed_by"] = actor
            validated_data["performed_at"] = timezone.now()
        with transaction.atomic():
            inspection = super().update(instance, validated_data)
            if inspection.inspection_type == RentalInspection.Type.PRE_RENTAL:
                order = ServiceOrder.objects.select_for_update().filter(rental_inspection=inspection).first()
                if not order:
                    raise serializers.ValidationError("O chamado de manutenção desta inspeção não foi encontrado.")
                if result in {RentalInspection.Result.APPROVED, RentalInspection.Result.APPROVED_WITH_NOTES}:
                    order.status = ServiceOrder.Status.COMPLETED
                    order.technician = actor
                    order.final_tests = f"Checklist pré-locação concluído: {inspection.get_result_display()}."
                    order.released = True
                elif result == RentalInspection.Result.BLOCKED:
                    order.status = ServiceOrder.Status.IN_PROGRESS
                    order.technician = actor
                    order.priority = "CRÍTICA"
                    order.diagnosis = inspection.observations or "Impedimento identificado na inspeção pré-locação."
                    order.released = False
                else:
                    order.status = ServiceOrder.Status.OPEN
                    order.released = False
                order.save()
                refresh_equipment_status(inspection.equipment)
            return inspection


class RentalExtensionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)

    class Meta:
        model = RentalExtension
        fields = "__all__"


class RentalQuoteSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    reserved_by_name = serializers.CharField(source="reserved_by.full_name", read_only=True)
    delivered_by_name = serializers.CharField(source="delivered_by.full_name", read_only=True)
    returned_by_name = serializers.CharField(source="returned_by.full_name", read_only=True)
    items = RentalItemSerializer(many=True)
    inspections = RentalInspectionSerializer(many=True, read_only=True)
    extensions = RentalExtensionSerializer(many=True, read_only=True)
    transport_tasks = TransportTaskSerializer(many=True, read_only=True)

    class Meta:
        model = RentalQuote
        fields = "__all__"
        read_only_fields = (
            "number", "public_id", "created_by", "subtotal", "total", "created_at", "updated_at",
            "reserved_by", "reserved_at", "delivered_by", "delivered_at", "delivery_conditions",
            "returned_by", "returned_at", "return_conditions", "cancelled_by", "cancelled_at",
        )

    def validate_delivery_cep(self, value):
        if value and not re.fullmatch(r"\d{8}", value):
            raise serializers.ValidationError("Informe um CEP com 8 dígitos.")
        return value

    def validate_return_cep(self, value):
        if value and not re.fullmatch(r"\d{8}", value):
            raise serializers.ValidationError("Informe um CEP com 8 dígitos.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "A data final deve ser igual ou posterior à inicial."})
        items = attrs.get("items")
        status = attrs.get("status", getattr(self.instance, "status", RentalQuote.Status.DRAFT))
        if self.instance and status != self.instance.status and self.instance.status not in {RentalQuote.Status.DRAFT, RentalQuote.Status.SENT}:
            raise serializers.ValidationError({"status": "Use as ações do fluxo para alterar uma reserva ou locação."})
        if self.instance and status == RentalQuote.Status.CANCELLED:
            raise serializers.ValidationError({"status": "Use a ação de cancelamento e registre o motivo."})
        if status in {RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED, RentalQuote.Status.COMPLETED}:
            raise serializers.ValidationError({"status": "Use as ações de entrega e devolução para avançar a locação."})
        if self.instance and self.instance.status == RentalQuote.Status.APPROVED and any(
            key in attrs for key in (
                "items", "customer", "start_date", "end_date", "status", "delivery_transport_required",
                "return_transport_required", "delivery_address", "return_address", "delivery_complement", "return_complement",
                "delivery_cep", "return_cep", "transport_fee",
            )
        ):
            raise serializers.ValidationError("A reserva aprovada não pode trocar cliente, equipamentos ou período. Cancele e gere outro orçamento.")
        if not self.instance and not items:
            raise serializers.ValidationError({"items": "Inclua pelo menos um equipamento."})
        effective_items = items if items is not None else ([{"equipment": item.equipment, "daily_rate": item.daily_rate} for item in self.instance.items.all()] if self.instance else [])
        equipment_ids = [item["equipment"].pk for item in effective_items]
        if len(equipment_ids) != len(set(equipment_ids)):
            raise serializers.ValidationError({"items": "O mesmo equipamento não pode aparecer mais de uma vez."})
        days = (end - start).days + 1 if start and end else 0
        calculated_subtotal = sum((item.get("daily_rate", item["equipment"].daily_rate) * days for item in effective_items), Decimal("0"))
        transport_fee = attrs.get("transport_fee", getattr(self.instance, "transport_fee", Decimal("0")))
        discount_percent = attrs.get("discount_percent", getattr(self.instance, "discount_percent", None))
        if discount_percent is not None:
            if discount_percent < 0 or discount_percent > 100:
                raise serializers.ValidationError({"discount_percent": "O desconto deve ficar entre 0% e 100%."})
            attrs["discount"] = ((calculated_subtotal + transport_fee) * discount_percent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        discount = attrs.get("discount", getattr(self.instance, "discount", Decimal("0")))
        if transport_fee < 0:
            raise serializers.ValidationError({"transport_fee": "O frete não pode ser negativo."})
        if transport_fee and not (
            attrs.get("delivery_transport_required", getattr(self.instance, "delivery_transport_required", False))
            or attrs.get("return_transport_required", getattr(self.instance, "return_transport_required", False))
        ):
            raise serializers.ValidationError({"transport_fee": "Marque entrega ou coleta para cobrar transporte."})
        if attrs.get("delivery_transport_required", getattr(self.instance, "delivery_transport_required", False)) and not attrs.get(
            "delivery_address", getattr(self.instance, "delivery_address", "")
        ).strip():
            raise serializers.ValidationError({"delivery_address": "Informe o endereço da entrega."})
        if attrs.get("return_transport_required", getattr(self.instance, "return_transport_required", False)) and not attrs.get(
            "return_address", getattr(self.instance, "return_address", "")
        ).strip():
            raise serializers.ValidationError({"return_address": "Informe o endereço da coleta."})
        if discount < 0:
            raise serializers.ValidationError({"discount": "O desconto não pode ser negativo."})
        if effective_items and discount > calculated_subtotal + transport_fee:
            raise serializers.ValidationError({"discount": "O desconto não pode superar o valor dos equipamentos e frete."})
        if status == RentalQuote.Status.APPROVED:
            request = self.context.get("request")
            if request and not request.user.has_acl("rentals.approve"):
                raise serializers.ValidationError({"status": "Seu grupo não pode aprovar orçamentos ou reservar equipamentos."})
            equipment_items = effective_items
            conflicts = {}
            for item in equipment_items:
                equipment = item["equipment"]
                reason = availability_reason(equipment, start, end, self.instance)
                if reason:
                    conflicts[equipment.internal_code] = reason
            if conflicts:
                raise serializers.ValidationError({"availability": conflicts})
            conditions = attrs.get("conditions", getattr(self.instance, "conditions", ""))
            if not conditions.strip():
                raise serializers.ValidationError({"conditions": "Registre as condições da reserva."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items")
        quote = RentalQuote.objects.create(created_by=self.context["request"].user, **validated_data)
        self._replace_items(quote, items)
        self._sync_reservation(quote)
        return quote

    @transaction.atomic
    def update(self, instance, validated_data):
        previous_status = instance.status
        items = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items is not None:
            instance.items.all().delete()
            self._replace_items(instance, items)
        else:
            if instance.status == RentalQuote.Status.APPROVED:
                equipment_ids = sorted(instance.items.values_list("equipment_id", flat=True))
                for equipment in Equipment.objects.select_for_update().filter(pk__in=equipment_ids).order_by("pk"):
                    reason = availability_reason(equipment, instance.start_date, instance.end_date, instance)
                    if reason:
                        raise serializers.ValidationError({"availability": {equipment.internal_code: reason}})
            instance.recalculate()
        if instance.status == RentalQuote.Status.APPROVED:
            self._sync_reservation(instance)
        elif previous_status == RentalQuote.Status.APPROVED and instance.status in {RentalQuote.Status.CANCELLED, RentalQuote.Status.EXPIRED}:
            for line in instance.items.select_related("equipment"):
                refresh_equipment_status(line.equipment)
        return instance

    def _sync_reservation(self, quote):
        changed = []
        if not quote.reserved_by_id:
            quote.reserved_by = self.context["request"].user
            changed.append("reserved_by")
        if not quote.reserved_at:
            quote.reserved_at = timezone.now()
            changed.append("reserved_at")
        if changed:
            quote.save(update_fields=(*changed, "updated_at"))
        ensure_inspections(quote, RentalInspection.Type.PRE_RENTAL)
        ensure_pre_rental_orders(quote, self.context["request"].user)
        ensure_transport_task(quote, TransportTask.Leg.DELIVERY, self.context["request"].user)
        for line in quote.items.select_related("equipment"):
            refresh_equipment_status(line.equipment)

    @staticmethod
    def _replace_items(quote, items):
        days = (quote.end_date - quote.start_date).days + 1
        equipment_ids = sorted(item["equipment"].pk for item in items)
        locked_equipment = {
            item.pk: item for item in Equipment.objects.select_for_update().filter(pk__in=equipment_ids).order_by("pk")
        }
        for item in items:
            equipment = locked_equipment[item["equipment"].pk]
            if quote.status == RentalQuote.Status.APPROVED:
                reason = availability_reason(equipment, quote.start_date, quote.end_date, quote)
                if reason:
                    raise serializers.ValidationError({"availability": {equipment.internal_code: reason}})
            item["equipment"] = equipment
            item["quantity_days"] = days
            item.setdefault("daily_rate", item["equipment"].daily_rate)
            RentalItem.objects.create(quote=quote, **item)
        quote.recalculate()
