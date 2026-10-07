from io import BytesIO

import qrcode
from django.conf import settings
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import ACLPermission
from .models import Equipment, EquipmentCategory, MediaAsset
from .serializers import EquipmentCategorySerializer, EquipmentSerializer, MediaAssetSerializer


class CategoryViewSet(ModelViewSet):
    queryset = EquipmentCategory.objects.all()
    serializer_class = EquipmentCategorySerializer
    permission_classes = [ACLPermission]
    acl_view = "assets.view"
    acl_manage = "assets.manage"


class EquipmentViewSet(ModelViewSet):
    queryset = Equipment.objects.select_related("category").annotate(media_count=Count("media", distinct=True)).order_by("internal_code")
    serializer_class = EquipmentSerializer
    permission_classes = [ACLPermission]
    acl_view = "assets.view"
    acl_manage = "assets.manage"

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.query_params.get("status")
        category = self.request.query_params.get("category")
        search = self.request.query_params.get("search")
        if status:
            queryset = queryset.filter(status=status)
        if category:
            queryset = queryset.filter(category_id=category)
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(internal_code__icontains=search) | Q(serial_number__icontains=search))
        return queryset

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        equipment = self.get_object()
        return Response({
            "service_orders": list(equipment.service_orders.values("id", "number", "maintenance_type", "status", "opened_at")),
            "rental_items": list(equipment.rental_items.values("quote_id", "quote__number", "quote__status", "quote__start_date", "quote__end_date")),
        })

    @action(detail=True, methods=["get"], url_path="qr-code")
    def qr_code(self, request, pk=None):
        equipment = self.get_object()
        target = f"{settings.FRONTEND_URL.rstrip('/')}/equipamentos?qr={equipment.qr_code_token}"
        image = qrcode.make(target)
        output = BytesIO()
        image.save(output, format="PNG")
        response = HttpResponse(output.getvalue(), content_type="image/png")
        response["Content-Disposition"] = f'inline; filename="qr-{equipment.internal_code}.png"'
        response["X-QR-Target"] = target
        return response

    @action(detail=False, methods=["get"], url_path="resolve-qr")
    def resolve_qr(self, request):
        token = request.query_params.get("token")
        try:
            equipment = self.get_queryset().get(qr_code_token=token)
        except (Equipment.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "QR Code inválido ou equipamento não encontrado."}, status=404)
        return Response(self.get_serializer(equipment).data)


class MediaAssetViewSet(ModelViewSet):
    queryset = MediaAsset.objects.select_related("equipment", "service_order", "rental_quote", "rental_inspection", "uploaded_by")
    serializer_class = MediaAssetSerializer
    permission_classes = [ACLPermission]
    acl_view = "media.view"
    acl_manage = "media.manage"

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset()
        for param, field in (("category", "category"), ("equipment", "equipment_id"), ("service_order", "service_order_id"), ("rental_quote", "rental_quote_id"), ("rental_inspection", "rental_inspection_id")):
            value = self.request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset
