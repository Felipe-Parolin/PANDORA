from rest_framework import serializers
from .models import Equipment, EquipmentCategory, MediaAsset


class EquipmentCategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)

    class Meta:
        model = EquipmentCategory
        fields = "__all__"

    def validate_parent(self, parent):
        if not parent:
            return parent
        instance = self.instance
        if instance and (parent.pk == instance.pk or parent.parent_id == (instance.pk if instance else None)):
            raise serializers.ValidationError("Uma categoria não pode ser sua própria subcategoria.")
        ancestor = parent
        while ancestor:
            if instance and ancestor.pk == instance.pk:
                raise serializers.ValidationError("Não é permitido criar ciclos na hierarquia de categorias.")
            ancestor = ancestor.parent
        return parent


class EquipmentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    qr_code_token = serializers.UUIDField(read_only=True)
    media_count = serializers.IntegerField(read_only=True)
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Equipment
        fields = "__all__"

    def get_photo_url(self, obj):
        photos = [item for item in obj.media.all() if item.category == MediaAsset.Category.PHOTO and item.file]
        if not photos:
            return None
        url = photos[0].file.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


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
        links = [attrs.get(name, getattr(self.instance, name, None)) for name in ("equipment", "service_order", "rental_quote", "rental_inspection")]
        if sum(bool(item) for item in links) != 1:
            raise serializers.ValidationError("Vincule a mídia a exatamente um equipamento, ordem, locação ou inspeção.")
        return attrs
