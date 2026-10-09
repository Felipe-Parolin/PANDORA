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
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    technician_name = serializers.CharField(source="technician.full_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    maintenance_type_label = serializers.CharField(source="get_maintenance_type_display", read_only=True)
    rental_quote_id = serializers.IntegerField(source="rental_inspection.quote_id", read_only=True)
    rental_quote_number = serializers.CharField(source="rental_inspection.quote.number", read_only=True)
    rental_quote_status = serializers.CharField(source="rental_inspection.quote.status", read_only=True)
    rental_customer_name = serializers.CharField(source="rental_inspection.quote.customer.name", read_only=True)
    rental_start_date = serializers.DateField(source="rental_inspection.quote.start_date", read_only=True)
    rental_end_date = serializers.DateField(source="rental_inspection.quote.end_date", read_only=True)
    inspection_result = serializers.CharField(source="rental_inspection.result", read_only=True)
    activities = MaintenanceActivitySerializer(many=True, required=False)

    class Meta:
        model = ServiceOrder
        fields = "__all__"
        read_only_fields = ("opened_by", "number", "public_id", "opened_at", "rental_inspection")

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
        if self.instance:
            immutable_fields = {"equipment", "maintenance_type", "symptoms"}
            attempted_changes = immutable_fields.intersection(attrs)
            if attempted_changes:
                raise serializers.ValidationError({
                    field: "Este dado é definido na abertura da OS e não pode ser alterado."
                    for field in attempted_changes
                })
        if self.instance and self.instance.rental_inspection_id:
            inspection = self.instance.rental_inspection
            if inspection.inspection_type == "PRE_RENTAL":
                cancelled_repair = inspection.quote.status == "CANCELLED" and inspection.result == "BLOCKED"
                if inspection.quote.status != "APPROVED" and not cancelled_repair:
                    raise serializers.ValidationError("Este chamado de pré-locação está encerrado para alterações.")
                if any(key in attrs for key in ("equipment", "maintenance_type")) or ("released" in attrs and not cancelled_repair):
                    raise serializers.ValidationError("O equipamento, o tipo e a liberação deste chamado são controlados pela reserva.")
                requested_status = attrs.get("status", self.instance.status)
                if cancelled_repair and requested_status == ServiceOrder.Status.CANCELLED:
                    raise serializers.ValidationError({"status": "Uma falha confirmada exige reparo e liberação técnica."})
                if cancelled_repair and requested_status == ServiceOrder.Status.COMPLETED and not attrs.get("released", self.instance.released):
                    raise serializers.ValidationError({"released": "Conclua os testes e libere o equipamento após o reparo."})
                if not cancelled_repair and requested_status in {ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED} and requested_status != self.instance.status:
                    raise serializers.ValidationError({"status": "Conclua a inspeção para liberar este chamado."})
                if inspection.result in {"APPROVED", "APPROVED_WITH_NOTES"} and requested_status != self.instance.status:
                    raise serializers.ValidationError({"status": "O chamado já foi liberado pela inspeção."})
            elif inspection.inspection_type == "RETURN" and inspection.result == "PENDING":
                requested_status = attrs.get("status", self.instance.status)
                if requested_status in {ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED} or attrs.get("released"):
                    raise serializers.ValidationError({"status": "Conclua a inspeção final antes de encerrar esta OS."})
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
