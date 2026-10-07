from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers
from .models import MaintenanceActivity, MaintenancePlan, ServiceOrder
from .patterns import ServiceOrderOpeningDirector
from .services import maintenance_alert_status, plan_due_date, plan_due_usage_hours


class MaintenanceActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceActivity
        fields = "__all__"
        read_only_fields = ("service_order",)


class MaintenancePlanSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    maintenance_type_label = serializers.CharField(source="get_maintenance_type_display", read_only=True)
    criticality_label = serializers.CharField(source="get_criticality_display", read_only=True)
    alert_status = serializers.SerializerMethodField()
    due_date = serializers.SerializerMethodField()
    due_usage_hours = serializers.SerializerMethodField()
    usage_remaining = serializers.SerializerMethodField()

    class Meta:
        model = MaintenancePlan
        fields = "__all__"

    def get_alert_status(self, obj):
        return maintenance_alert_status(obj)

    def get_due_date(self, obj):
        return plan_due_date(obj)

    def get_due_usage_hours(self, obj):
        return plan_due_usage_hours(obj)

    def get_usage_remaining(self, obj):
        due = plan_due_usage_hours(obj)
        return None if due is None else due - obj.equipment.current_usage_hours

    def validate(self, attrs):
        interval = attrs.get("interval_days", getattr(self.instance, "interval_days", None))
        usage = attrs.get("usage_limit", getattr(self.instance, "usage_limit", None))
        due_date = attrs.get("next_due_date", getattr(self.instance, "next_due_date", None))
        if not any((interval, usage, due_date)):
            raise serializers.ValidationError("Informe periodicidade em dias, limite de uso ou próxima data.")
        return attrs


class ServiceOrderSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="equipment.name", read_only=True)
    technician_name = serializers.CharField(source="technician.full_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    maintenance_type_label = serializers.CharField(source="get_maintenance_type_display", read_only=True)
    activities = MaintenanceActivitySerializer(many=True, required=False)

    class Meta:
        model = ServiceOrder
        fields = "__all__"
        read_only_fields = ("opened_by", "number", "public_id", "opened_at")

    def create(self, validated_data):
        activities = validated_data.pop("activities", [])
        request = self.context["request"]
        order = ServiceOrderOpeningDirector().open(
            equipment=validated_data.pop("equipment"),
            opened_by=request.user,
            technician=validated_data.pop("technician", None),
            symptoms=validated_data.pop("symptoms"),
            maintenance_type=validated_data.pop("maintenance_type"),
            **validated_data,
        )
        MaintenanceActivity.objects.bulk_create([MaintenanceActivity(service_order=order, **item) for item in activities])
        return order

    def update(self, instance, validated_data):
        previous_status = instance.status
        order = super().update(instance, validated_data)
        if previous_status != ServiceOrder.Status.COMPLETED and order.status == ServiceOrder.Status.COMPLETED and order.plan_id:
            plan = order.plan
            plan.last_service_date = timezone.localdate()
            plan.last_service_usage_hours = order.equipment.current_usage_hours
            if plan.interval_days:
                plan.next_due_date = plan.last_service_date + timedelta(days=plan.interval_days)
            plan.save(update_fields=("last_service_date", "last_service_usage_hours", "next_due_date"))
        return order

    def validate(self, attrs):
        released = attrs.get("released", getattr(self.instance, "released", False))
        status = attrs.get("status", getattr(self.instance, "status", None))
        tests = attrs.get("final_tests", getattr(self.instance, "final_tests", ""))
        technician = attrs.get("technician", getattr(self.instance, "technician", None))
        abandoned_reason = attrs.get("abandoned_reason", getattr(self.instance, "abandoned_reason", ""))
        request = self.context.get("request")
        if status in {ServiceOrder.Status.IN_PROGRESS, ServiceOrder.Status.WAITING_PARTS, ServiceOrder.Status.ABANDONED} and not technician:
            raise serializers.ValidationError({"technician": "Esta etapa exige um técnico responsável."})
        if status == ServiceOrder.Status.ABANDONED and not abandoned_reason.strip():
            raise serializers.ValidationError({"abandoned_reason": "Informe por que o técnico abandonou o chamado."})
        if released and request and not request.user.has_acl("maintenance.release"):
            raise serializers.ValidationError({"released": "Seu grupo não possui permissão para liberar equipamentos."})
        if released and (status != ServiceOrder.Status.COMPLETED or not tests.strip() or not technician):
            raise serializers.ValidationError("A liberação exige OS concluída, testes finais e técnico responsável.")
        return attrs
