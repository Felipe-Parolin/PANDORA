from rest_framework import serializers
from assets.models import EquipmentCategory
from .models import EquipmentPackage, EquipmentPackageComponent, PurchaseRecommendation, MarketingCampaign

class PackageComponentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    class Meta:
        model = EquipmentPackageComponent
        fields = ("id", "category", "category_name", "quantity", "reference_daily_rate")

class EquipmentPackageSerializer(serializers.ModelSerializer):
    components = PackageComponentSerializer(many=True)
    reference_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    class Meta:
        model = EquipmentPackage
        fields = "__all__"
        read_only_fields = ("created_by", "created_at", "updated_at")
    def validate(self, attrs):
        components = attrs.get("components", [])
        if not components and not self.instance:
            raise serializers.ValidationError({"components": "Adicione ao menos uma categoria ao pacote."})
        ids = [x["category"].pk for x in components]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({"components": "Não repita categorias no mesmo pacote."})
        if attrs.get("promotional_discount_percent", getattr(self.instance, "promotional_discount_percent", 0)) > 100:
            raise serializers.ValidationError({"promotional_discount_percent": "O desconto máximo é 100%."})
        return attrs
    def create(self, validated_data):
        components = validated_data.pop("components")
        package = EquipmentPackage.objects.create(**validated_data)
        EquipmentPackageComponent.objects.bulk_create([EquipmentPackageComponent(package=package, **item) for item in components])
        return package
    def update(self, instance, validated_data):
        components = validated_data.pop("components", None)
        instance = super().update(instance, validated_data)
        if components is not None:
            instance.components.all().delete()
            EquipmentPackageComponent.objects.bulk_create([EquipmentPackageComponent(package=instance, **item) for item in components])
        return instance

class PurchaseRecommendationSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True)
    class Meta:
        model = PurchaseRecommendation
        fields = "__all__"
        read_only_fields = ("current_total", "current_available", "demand_events", "maintenance_orders", "unavailable_days", "evidence", "rationale", "created_at", "updated_at", "decided_by", "decided_at")

class MarketingCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketingCampaign
        fields = "__all__"
        read_only_fields = ("status", "sent_at", "recipient_count", "result_log", "created_by", "created_at")
