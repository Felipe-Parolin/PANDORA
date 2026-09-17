from django.utils import timezone
from rest_framework import serializers
from .models import MaintenanceActivity, MaintenancePlan, ServiceOrder
from .patterns import ServiceOrderOpeningDirector


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

    class Meta:
        model = MaintenancePlan
        fields = "__all__"

    def get_alert_status(self, obj):
        if not obj.active or not obj.next_due_date:
            return "OK"
        days = (obj.next_due_date - timezone.localdate()).days
        if days < 0:
            return "CRITICAL" if obj.criticality == MaintenancePlan.Criticality.CRITICAL else "OVERDUE"
        return "UPCOMING" if days <= 15 else "OK"


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
