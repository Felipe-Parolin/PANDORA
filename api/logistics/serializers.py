import re

from rest_framework import serializers

from .models import TransportTask, Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    vehicle_type_label = serializers.CharField(source="get_vehicle_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    in_transit = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = "__all__"
        read_only_fields = ("created_at",)

    def get_in_transit(self, obj):
        return obj.transport_tasks.filter(status=TransportTask.Status.IN_TRANSIT).exists()

    def validate_plate(self, value):
        plate = value.replace("-", "").replace(" ", "").upper()
        if not re.fullmatch(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", plate):
            raise serializers.ValidationError("Informe uma placa brasileira válida, como ABC1234 ou ABC1D23.")
        return plate

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", Vehicle.Status.AVAILABLE))
        if self.instance and status != Vehicle.Status.AVAILABLE and self.instance.transport_tasks.filter(
            status=TransportTask.Status.IN_TRANSIT
        ).exists():
            raise serializers.ValidationError({"status": "Finalize a viagem em andamento antes de indisponibilizar o veículo."})
        return attrs


class TransportTaskSerializer(serializers.ModelSerializer):
    quote_number = serializers.CharField(source="quote.number", read_only=True)
    quote_status = serializers.CharField(source="quote.status", read_only=True)
    customer_name = serializers.CharField(source="quote.customer.name", read_only=True)
    vehicle_plate = serializers.CharField(source="vehicle.plate", read_only=True)
    driver_name = serializers.CharField(source="driver.full_name", read_only=True)
    leg_label = serializers.CharField(source="get_leg_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = TransportTask
        fields = "__all__"
        read_only_fields = (
            "quote", "leg", "status", "departed_at", "completed_at", "created_by", "created_at",
        )

    def validate(self, attrs):
        if self.instance and self.instance.status != TransportTask.Status.PLANNED:
            raise serializers.ValidationError("Apenas viagens planejadas podem ser alteradas.")
        vehicle = attrs.get("vehicle", getattr(self.instance, "vehicle", None))
        driver = attrs.get("driver", getattr(self.instance, "driver", None))
        if vehicle and vehicle.status != Vehicle.Status.AVAILABLE:
            raise serializers.ValidationError({"vehicle": "O veículo não está disponível."})
        if vehicle and vehicle.transport_tasks.filter(status=TransportTask.Status.IN_TRANSIT).exclude(
            pk=getattr(self.instance, "pk", None)
        ).exists():
            raise serializers.ValidationError({"vehicle": "Este veículo já está em transporte."})
        if driver and not driver.is_active:
            raise serializers.ValidationError({"driver": "Selecione um funcionário ativo."})
        if not attrs.get("address", getattr(self.instance, "address", "")).strip():
            raise serializers.ValidationError({"address": "Informe o endereço da entrega ou coleta."})
        return attrs
