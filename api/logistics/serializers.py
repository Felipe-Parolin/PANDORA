import re

from rest_framework import serializers
from django.db import models, transaction
from datetime import timedelta

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
    address_cep = serializers.RegexField(r"^\d{8}$", required=False, allow_blank=True, max_length=8)
    items = serializers.SerializerMethodField()
    rental_item_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), write_only=True, required=False, allow_empty=False)

    def get_items(self, obj):
        from .services import task_items
        return [{"id": line.pk, "equipment": line.equipment_id, "equipment_name": line.equipment.name, "internal_code": line.equipment.internal_code, "start_date": line.start_date, "end_date": line.end_date, "stage": line.stage} for line in task_items(obj)]

    def validate_rental_item_ids(self, ids):
        from .services import task_items
        allowed = {line.pk for line in task_items(self.instance)} if self.instance else set()
        if len(ids) != len(set(ids)) or not set(ids).issubset(allowed):
            raise serializers.ValidationError("Selecione apenas equipamentos desta viagem, sem repetições.")
        return ids

    @transaction.atomic
    def update(self, instance, validated_data):
        from .services import task_items, ensure_transport_task
        from rentals.models import RentalQuote
        RentalQuote.objects.select_for_update().get(pk=instance.quote_id)
        instance = TransportTask.objects.select_for_update().get(pk=instance.pk)
        self.instance = instance
        validated_data = self.validate(validated_data)
        if "rental_item_ids" in validated_data:
            self.validate_rental_item_ids(validated_data["rental_item_ids"])
        ids = validated_data.pop("rental_item_ids", None)
        previous = list(task_items(instance)) if ids is not None else []
        task = super().update(instance, validated_data)
        if ids is not None:
            selected = [line for line in previous if line.pk in ids]
            task.items_scoped = True; task.save(update_fields=("items_scoped",))
            task.rental_items.set(selected)
            ensure_transport_task(task.quote, task.leg, self.context["request"].user, items=[line for line in previous if line.pk not in ids], exclude_merge_ids={task.pk})
        return task

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
            "latitude", "longitude", "geocoded_address", "rental_items", "items_scoped", "batch_date", "batch_key",
        )

    def validate(self, attrs):
        if self.instance and self.instance.status != TransportTask.Status.PLANNED:
            raise serializers.ValidationError("Apenas viagens planejadas podem ser alteradas.")
        vehicle = attrs.get("vehicle", getattr(self.instance, "vehicle", None))
        driver = attrs.get("driver", getattr(self.instance, "driver", None))
        if vehicle and vehicle.status != Vehicle.Status.AVAILABLE:
            raise serializers.ValidationError({"vehicle": "O veículo não está disponível."})
        scheduled_at = attrs.get("scheduled_at", getattr(self.instance, "scheduled_at", None))
        scheduled_end_at = attrs.get("scheduled_end_at", getattr(self.instance, "scheduled_end_at", None))
        if scheduled_end_at and scheduled_at and scheduled_end_at <= scheduled_at:
            raise serializers.ValidationError({"scheduled_end_at": "O término deve ser posterior ao início da viagem."})
        if scheduled_at and not vehicle:
            raise serializers.ValidationError({"vehicle": "Selecione um veículo para uma viagem agendada."})
        if scheduled_at and not driver:
            raise serializers.ValidationError({"driver": "Selecione um motorista para uma viagem agendada."})
        if vehicle and scheduled_at:
            conflicts = vehicle.transport_tasks.filter(status__in=(TransportTask.Status.PLANNED, TransportTask.Status.IN_TRANSIT)).exclude(pk=getattr(self.instance, "pk", None)).filter(scheduled_at__isnull=False).filter(
                scheduled_at__lt=scheduled_end_at or scheduled_at + timedelta(hours=2)
            ).filter(models.Q(scheduled_end_at__gt=scheduled_at) | models.Q(scheduled_end_at__isnull=True, scheduled_at__gt=scheduled_at - timedelta(hours=2)))
            if attrs.get("trip_reference", getattr(self.instance, "trip_reference", "")):
                conflicts = conflicts.exclude(trip_reference=attrs.get("trip_reference", getattr(self.instance, "trip_reference", "")), driver=driver, scheduled_at=scheduled_at, leg=getattr(self.instance, "leg", None))
            if conflicts.exists():
                raise serializers.ValidationError({"vehicle": "Este veículo já possui viagem planejada ou em andamento nesse intervalo."})
        if driver and scheduled_at:
            conflicts = driver.driving_tasks.filter(status__in=(TransportTask.Status.PLANNED, TransportTask.Status.IN_TRANSIT)).exclude(pk=getattr(self.instance, "pk", None)).filter(scheduled_at__isnull=False).filter(
                scheduled_at__lt=scheduled_end_at or scheduled_at + timedelta(hours=2)
            ).filter(models.Q(scheduled_end_at__gt=scheduled_at) | models.Q(scheduled_end_at__isnull=True, scheduled_at__gt=scheduled_at - timedelta(hours=2)))
            if attrs.get("trip_reference", getattr(self.instance, "trip_reference", "")):
                conflicts = conflicts.exclude(trip_reference=attrs.get("trip_reference", getattr(self.instance, "trip_reference", "")), vehicle=vehicle, scheduled_at=scheduled_at, leg=getattr(self.instance, "leg", None))
            if conflicts.exists():
                raise serializers.ValidationError({"driver": "Este motorista já possui viagem planejada ou em andamento nesse intervalo."})
        if driver and not driver.is_active:
            raise serializers.ValidationError({"driver": "Selecione um funcionário ativo."})
        if not attrs.get("address", getattr(self.instance, "address", "")).strip():
            raise serializers.ValidationError({"address": "Informe o endereço da entrega ou coleta."})
        manifest = attrs.get("load_manifest", getattr(self.instance, "load_manifest", [])) or []
        if not isinstance(manifest, list) or any(not isinstance(code, str) for code in manifest):
            raise serializers.ValidationError({"load_manifest": "Informe uma lista de códigos de equipamentos."})
        manifest = [code.strip().upper() for code in manifest if code.strip()]
        if self.instance and "rental_item_ids" in attrs and "load_manifest" not in attrs:
            from .services import task_items
            removed = {line.equipment.internal_code.upper() for line in task_items(self.instance) if line.pk not in attrs["rental_item_ids"]}
            manifest = [code for code in manifest if code not in removed]
        if len(manifest) != len(set(manifest)):
            raise serializers.ValidationError({"load_manifest": "Não repita códigos na ordem de carregamento."})
        if manifest and self.instance:
            trip_reference = attrs.get("trip_reference", self.instance.trip_reference)
            if trip_reference:
                group = TransportTask.objects.filter(
                    trip_reference=trip_reference,
                    vehicle=vehicle,
                    driver=driver,
                    scheduled_at=scheduled_at,
                    leg=self.instance.leg,
                ).exclude(pk=self.instance.pk)
            from .services import task_items
            current_lines = list(task_items(self.instance))
            if "rental_item_ids" in attrs:
                current_lines = [line for line in current_lines if line.pk in attrs["rental_item_ids"]]
            allowed = {line.equipment.internal_code.upper() for line in current_lines}
            if trip_reference:
                allowed.update(line.equipment.internal_code.upper() for stop in group.prefetch_related("rental_items__equipment", "quote__items__equipment") for line in task_items(stop))
            unknown = sorted(set(manifest) - allowed)
            if unknown:
                raise serializers.ValidationError({"load_manifest": f"Código(s) não pertencem às locações desta viagem: {', '.join(unknown)}."})
        attrs["load_manifest"] = manifest
        return attrs
