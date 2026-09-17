from django.db import transaction
from decimal import Decimal
from rest_framework import serializers

from assets.models import Equipment
from .models import RentalItem, RentalQuote
from .services import availability_reason


class RentalItemSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    internal_code = serializers.CharField(source="equipment.internal_code", read_only=True)
    equipment_id = serializers.PrimaryKeyRelatedField(source="equipment", queryset=Equipment.objects.all(), write_only=True)

    class Meta:
        model = RentalItem
        fields = ("id", "equipment", "equipment_id", "equipment_name", "internal_code", "daily_rate", "quantity_days", "total", "condition_out")
        read_only_fields = ("equipment", "total")


class RentalQuoteSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    items = RentalItemSerializer(many=True)

    class Meta:
        model = RentalQuote
        fields = "__all__"
        read_only_fields = ("number", "public_id", "created_by", "subtotal", "total", "created_at", "updated_at")

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "A data final deve ser igual ou posterior à inicial."})
        items = attrs.get("items")
        status = attrs.get("status", getattr(self.instance, "status", RentalQuote.Status.DRAFT))
        if not self.instance and not items:
            raise serializers.ValidationError({"items": "Inclua pelo menos um equipamento."})
        effective_items = items if items is not None else ([{"equipment": item.equipment, "daily_rate": item.daily_rate} for item in self.instance.items.all()] if self.instance else [])
        equipment_ids = [item["equipment"].pk for item in effective_items]
        if len(equipment_ids) != len(set(equipment_ids)):
            raise serializers.ValidationError({"items": "O mesmo equipamento não pode aparecer mais de uma vez."})
        days = (end - start).days + 1 if start and end else 0
        calculated_subtotal = sum((item.get("daily_rate", item["equipment"].daily_rate) * days for item in effective_items), Decimal("0"))
        discount = attrs.get("discount", getattr(self.instance, "discount", Decimal("0")))
        if discount < 0:
            raise serializers.ValidationError({"discount": "O desconto não pode ser negativo."})
        if effective_items and discount > calculated_subtotal:
            raise serializers.ValidationError({"discount": "O desconto não pode superar o subtotal do orçamento."})
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
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items")
        quote = RentalQuote.objects.create(created_by=self.context["request"].user, **validated_data)
        self._replace_items(quote, items)
        return quote

    @transaction.atomic
    def update(self, instance, validated_data):
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
        return instance

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
