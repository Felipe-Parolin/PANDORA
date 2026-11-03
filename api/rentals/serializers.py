from django.db import transaction
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
import re
from rest_framework import serializers
from core.serializer_fields import OptionalDateTimeField

from assets.models import Equipment
from maintenance.models import ServiceOrder
from logistics.serializers import TransportTaskSerializer
from logistics.services import ensure_transport_task
from logistics.models import TransportTask
from .models import RentalExtension, RentalInspection, RentalItem, RentalQuote
from .services import availability_reason, ensure_inspections, ensure_pre_rental_orders, refresh_equipment_status
from .addresses import full_address


def validate_location(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError("Informe um destino válido.")
    if not value:
        return {}
    limits = {"address": 255, "number": 20, "cep": 8, "complement": 120, "time": 5}
    if set(value) - limits.keys() or any(not isinstance(item, str) for item in value.values()):
        raise serializers.ValidationError("Use endereço, número, CEP, complemento e horário como texto.")
    result = {key: value.get(key, "").strip() for key in limits}
    if any(len(result[key]) > limit for key, limit in limits.items()) or len(full_address(result['address'], result['number'])) > 255:
        raise serializers.ValidationError("O endereço ou outro campo ultrapassou o tamanho permitido.")
    if result['cep'] and not re.fullmatch(r"\d{8}", result['cep']):
        raise serializers.ValidationError("Informe um CEP com oito dígitos.")
    if result['time'] and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", result['time']):
        raise serializers.ValidationError("Informe um horário válido (HH:MM).")
    return result


class RentalItemSerializer(serializers.ModelSerializer):
    delivery_location = serializers.JSONField(required=False, validators=[validate_location])
    return_location = serializers.JSONField(required=False, validators=[validate_location])
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    internal_code = serializers.CharField(source="equipment.internal_code", read_only=True)
    equipment_id = serializers.PrimaryKeyRelatedField(source="equipment", queryset=Equipment.objects.all(), write_only=True)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    daily_rate = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False)
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)

    class Meta:
        model = RentalItem
        fields = ("id", "equipment", "equipment_id", "equipment_name", "internal_code", "daily_rate", "quantity_days", "total", "condition_out", "start_date", "end_date", "stage", "stage_label", "delivered_at", "returned_at", "finalized_at", "delivery_location", "return_location")
        read_only_fields = ("equipment", "quantity_days", "total", "condition_out", "stage", "delivered_at", "returned_at", "finalized_at")


class RentalInspectionSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    internal_code = serializers.CharField(source="equipment.internal_code", read_only=True)
    category_name = serializers.CharField(source="equipment.category.name", read_only=True)
    inspection_type_label = serializers.CharField(source="get_inspection_type_display", read_only=True)
    result_label = serializers.CharField(source="get_result_display", read_only=True)
    condition_label = serializers.CharField(source="get_condition_display", read_only=True)
    performed_by_name = serializers.CharField(source="performed_by.full_name", read_only=True)
    media_count = serializers.SerializerMethodField()
    item_stage = serializers.SerializerMethodField()

    class Meta:
        model = RentalInspection
        fields = "__all__"
        read_only_fields = ("quote", "equipment", "inspection_type", "performed_by", "performed_at", "created_at", "updated_at")

    def get_item_stage(self, obj):
        line = next((line for line in obj.quote.items.all() if line.equipment_id == obj.equipment_id), None)
        return line.stage if line else None

    def get_media_count(self, obj):
        return obj.media.count()

    def validate(self, attrs):
        if self.instance:
            line = self.instance.quote.items.filter(equipment=self.instance.equipment).first()
            allowed = line and (
                self.instance.inspection_type == "PRE_RENTAL" and line.stage == "PENDING" and self.instance.quote.status in {"APPROVED", "ACTIVE"}
                or self.instance.inspection_type == "RETURN" and line.stage == "RETURNED" and self.instance.quote.status in {"ACTIVE", "RETURNED"}
            )
            if not allowed:
                raise serializers.ValidationError("Esta inspeção não está disponível na etapa atual do equipamento.")
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
        actor = self.context["request"].user
        with transaction.atomic():
            # Mesma ordem das movimentações: locação, patrimônio e inspeção.
            RentalQuote.objects.select_for_update().get(pk=instance.quote_id)
            Equipment.objects.select_for_update().get(pk=instance.equipment_id)
            instance = RentalInspection.objects.select_for_update().get(pk=instance.pk)
            self.instance = instance
            validated_data = self.validate(validated_data)
            result = validated_data.get("result", instance.result)
            if result != RentalInspection.Result.PENDING:
                validated_data["performed_by"] = actor
                validated_data["performed_at"] = timezone.now()
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
                    note = inspection.observations or "Impedimento identificado na inspeção pré-locação."
                    if note not in order.diagnosis:
                        order.diagnosis = f"{order.diagnosis.rstrip()}\n\nInspeção: {note}".strip()
                    order.released = False
                else:
                    order.status = ServiceOrder.Status.OPEN
                    order.released = False
                order.save()
                refresh_equipment_status(inspection.equipment)
            else:
                order = ServiceOrder.objects.select_for_update().filter(rental_inspection=inspection).first()
                if not order:
                    raise serializers.ValidationError("O chamado de inspeção final não foi encontrado na manutenção.")
                needs_repair = inspection.result == RentalInspection.Result.BLOCKED or inspection.condition in {
                    RentalInspection.Condition.DAMAGED, RentalInspection.Condition.CRITICAL,
                }
                if needs_repair:
                    order.status = ServiceOrder.Status.IN_PROGRESS
                    order.technician = actor
                    order.priority = "CRÍTICA" if inspection.critical_impediment else "ALTA"
                    note = inspection.observations or "Avaria identificada na inspeção de devolução."
                    if note not in order.diagnosis:
                        order.diagnosis = f"{order.diagnosis.rstrip()}\n\nInspeção: {note}".strip()
                    order.final_tests = ""
                    order.released = False
                elif inspection.result in {RentalInspection.Result.APPROVED, RentalInspection.Result.APPROVED_WITH_NOTES}:
                    order.status = ServiceOrder.Status.COMPLETED
                    order.technician = actor
                    order.final_tests = f"Checklist de devolução concluído: {inspection.get_result_display()}."
                    order.released = True
                else:
                    order.status = ServiceOrder.Status.OPEN
                    order.final_tests = ""
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
    requested_delivery_at = OptionalDateTimeField(required=False, allow_null=True)
    requested_return_at = OptionalDateTimeField(required=False, allow_null=True)
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

    def validate_delivery_number(self, value):
        return value.strip()

    def validate_return_number(self, value):
        return value.strip()

    def validate_return_cep(self, value):
        if value and not re.fullmatch(r"\d{8}", value):
            raise serializers.ValidationError("Informe um CEP com 8 dígitos.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "A data final deve ser igual ou posterior à inicial."})
        delivery_at = attrs.get("requested_delivery_at", getattr(self.instance, "requested_delivery_at", None))
        return_at = attrs.get("requested_return_at", getattr(self.instance, "requested_return_at", None))
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
                "delivery_cep", "return_cep", "transport_fee", "estimated_transport_fee", "transport_fee_adjustment_reason", "requested_delivery_at", "requested_return_at", "requested_delivery_notes",
                "delivery_number", "return_number",
            )
        ):
            raise serializers.ValidationError("A reserva aprovada não pode trocar cliente, equipamentos ou período. Cancele e gere outro orçamento.")
        if items is not None and not items or not self.instance and not items:
            raise serializers.ValidationError({"items": "Inclua pelo menos um equipamento."})
        effective_items = items if items is not None else [{"id": item.pk, "equipment": item.equipment, "daily_rate": item.daily_rate, "start_date": item.start_date, "end_date": item.end_date, "delivery_location": item.delivery_location, "return_location": item.return_location} for item in self.instance.items.select_related("equipment")]
        self._period_updates = {}
        equipment_ids = [item["equipment"].pk for item in effective_items]
        if len(equipment_ids) != len(set(equipment_ids)):
            raise serializers.ValidationError({"items": "O mesmo equipamento não pode aparecer mais de uma vez."})
        for index, item in enumerate(effective_items):
            if items is None and self.instance and ("start_date" in attrs or "end_date" in attrs) and (item["start_date"], item["end_date"]) == (self.instance.start_date, self.instance.end_date):
                item["start_date"], item["end_date"] = start, end
            item_start, item_end = item.get("start_date", start), item.get("end_date", end)
            if not item_start or not item_end or item_end < item_start:
                raise serializers.ValidationError({"items": {index: "Informe um período válido para o equipamento."}})
            item["start_date"], item["end_date"] = item_start, item_end
            if items is None:
                self._period_updates[item["id"]] = (item_start, item_end)
        if effective_items and (items is not None or "start_date" in attrs or "end_date" in attrs):
            start = attrs["start_date"] = min(item["start_date"] for item in effective_items)
            end = attrs["end_date"] = max(item["end_date"] for item in effective_items)
        for item in effective_items:
            for leg in ("delivery", "return"):
                item[f"{leg}_location"] = validate_location(item.get(f"{leg}_location", {}))
                custom = item[f"{leg}_location"]
                address = custom.get('address') if custom else attrs.get(f'{leg}_address', getattr(self.instance, f'{leg}_address', ''))
                number = custom.get('number') if custom else attrs.get(f'{leg}_number', getattr(self.instance, f'{leg}_number', ''))
                required = attrs.get(f'{leg}_transport_required', getattr(self.instance, f'{leg}_transport_required', False))
                if required and (not address or len(full_address(address, number)) > 255):
                    raise serializers.ValidationError({"items": f"Informe um endereço válido de {'entrega' if leg == 'delivery' else 'coleta'} para cada equipamento."})
                if required and custom and (not custom['number'] or not re.fullmatch(r'\d{8}',custom['cep'])):
                    raise serializers.ValidationError({"items": "Preencha número e CEP nos destinos específicos."})
            delivery_time = item['delivery_location'].get('time') if item['delivery_location'] else timezone.localtime(delivery_at).strftime('%H:%M') if delivery_at else ''
            return_time = item['return_location'].get('time') if item['return_location'] else timezone.localtime(return_at).strftime('%H:%M') if return_at else ''
            if item['start_date'] == item['end_date'] and delivery_time and return_time and return_time < delivery_time:
                raise serializers.ValidationError({"items": "A devolução de um item de um dia não pode anteceder sua retirada."})
        if delivery_at and return_at and return_at < delivery_at and any(not item['delivery_location'] and not item['return_location'] for item in effective_items):
            raise serializers.ValidationError({"requested_return_at": "O horário de devolução deve ser igual ou posterior ao de entrega."})
        calculated_subtotal = sum((item.get("daily_rate", item["equipment"].daily_rate) * ((item["end_date"]-item["start_date"]).days+1) for item in effective_items), Decimal("0"))
        transport_fee = attrs.get("transport_fee", getattr(self.instance, "transport_fee", Decimal("0")))
        estimated_transport_fee = attrs.get("estimated_transport_fee", getattr(self.instance, "estimated_transport_fee", Decimal("0")))
        adjustment_reason = attrs.get("transport_fee_adjustment_reason", getattr(self.instance, "transport_fee_adjustment_reason", ""))
        if "transport_fee" in attrs and "estimated_transport_fee" in attrs and self.instance and transport_fee != self.instance.transport_fee and transport_fee != estimated_transport_fee and not adjustment_reason.strip():
            raise serializers.ValidationError({"transport_fee_adjustment_reason": "Justifique o ajuste manual do frete em relação à estimativa."})
        if "transport_fee" in attrs and "estimated_transport_fee" in attrs and not self.instance and transport_fee != estimated_transport_fee and not adjustment_reason.strip():
            raise serializers.ValidationError({"transport_fee_adjustment_reason": "Justifique o ajuste manual do frete em relação à estimativa."})
        if estimated_transport_fee < 0:
            raise serializers.ValidationError({"estimated_transport_fee": "A estimativa não pode ser negativa."})
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
        if any(not item['delivery_location'] for item in effective_items) and attrs.get("delivery_transport_required", getattr(self.instance, "delivery_transport_required", False)) and not attrs.get(
            "delivery_address", getattr(self.instance, "delivery_address", "")
        ).strip():
            raise serializers.ValidationError({"delivery_address": "Informe o endereço da entrega."})
        if any(not item['return_location'] for item in effective_items) and attrs.get("return_transport_required", getattr(self.instance, "return_transport_required", False)) and not attrs.get(
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
                reason = availability_reason(equipment, item["start_date"], item["end_date"], self.instance)
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
            for line in instance.items.all():
                period = getattr(self, "_period_updates", {}).get(line.pk)
                if period and period != (line.start_date, line.end_date):
                    line.start_date, line.end_date = period
                    line.save(update_fields=("start_date", "end_date"))
            if instance.status == RentalQuote.Status.APPROVED:
                equipment_ids = sorted(instance.items.values_list("equipment_id", flat=True))
                for equipment in Equipment.objects.select_for_update().filter(pk__in=equipment_ids).order_by("pk"):
                    line = instance.items.get(equipment=equipment)
                    reason = availability_reason(equipment, line.start_date, line.end_date, instance)
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
        if quote.status != RentalQuote.Status.APPROVED:
            return
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
        equipment_ids = sorted(item["equipment"].pk for item in items)
        locked_equipment = {
            item.pk: item for item in Equipment.objects.select_for_update().filter(pk__in=equipment_ids).order_by("pk")
        }
        for item in items:
            equipment = locked_equipment[item["equipment"].pk]
            if quote.status == RentalQuote.Status.APPROVED:
                reason = availability_reason(equipment, item.get("start_date", quote.start_date), item.get("end_date", quote.end_date), quote)
                if reason:
                    raise serializers.ValidationError({"availability": {equipment.internal_code: reason}})
            item["equipment"] = equipment
            item["start_date"] = item.get("start_date", quote.start_date)
            item["end_date"] = item.get("end_date", quote.end_date)
            item["quantity_days"] = (item["end_date"]-item["start_date"]).days+1
            item.setdefault("daily_rate", item["equipment"].daily_rate)
            RentalItem.objects.create(quote=quote, **item)
        quote.recalculate()
