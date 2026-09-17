from rest_framework import serializers
from .models import Equipment, EquipmentCategory, MediaAsset


class EquipmentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentCategory
        fields = "__all__"


class EquipmentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    qr_code_token = serializers.UUIDField(read_only=True)
    media_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Equipment
        fields = "__all__"


class MediaAssetSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = "__all__"
        read_only_fields = ("uploaded_by",)

    def get_file_url(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if request and obj.file else None

    def validate(self, attrs):
        links = [attrs.get(name, getattr(self.instance, name, None)) for name in ("equipment", "service_order", "rental_quote")]
        if sum(bool(item) for item in links) != 1:
            raise serializers.ValidationError("Vincule a mídia a exatamente um equipamento, ordem de serviço ou orçamento.")
        return attrs
