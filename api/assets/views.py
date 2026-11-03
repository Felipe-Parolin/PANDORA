from io import BytesIO
from pathlib import Path

import qrcode
from django.conf import settings
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import ACLPermission
from .models import Equipment, EquipmentCategory, MediaAsset
from .serializers import EquipmentCategorySerializer, EquipmentSerializer, MediaAssetSerializer


class CategoryViewSet(ModelViewSet):
    queryset = EquipmentCategory.objects.select_related('parent').all()
    serializer_class = EquipmentCategorySerializer
    permission_classes = [ACLPermission]
    acl_view = "assets.view"
    acl_manage = "assets.manage"


class EquipmentViewSet(ModelViewSet):
    queryset = Equipment.objects.select_related("category").prefetch_related("media").annotate(media_count=Count("media", distinct=True)).order_by("internal_code")
    serializer_class = EquipmentSerializer
    permission_classes = [ACLPermission]
    acl_view = "assets.view"
    acl_manage = "assets.manage"

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        status = params.get("status")
        category = params.get("category")
        search = params.get("search")
        for param, field in (
            ("brand", "brand__icontains"), ("model", "model__icontains"),
            ("serial_number", "serial_number__icontains"), ("internal_code", "internal_code__icontains"),
        ):
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{field: value.strip()})
        if status:
            queryset = queryset.filter(status=status)
        if category:
            queryset = queryset.filter(Q(category_id=category) | Q(category__parent_id=category))
        subcategory = params.get("subcategory")
        if subcategory:
            queryset = queryset.filter(category_id=subcategory)
        if search:
            search_filter = (
                Q(name__icontains=search) | Q(internal_code__icontains=search)
                | Q(serial_number__icontains=search) | Q(brand__icontains=search)
                | Q(model__icontains=search)
            )
            import uuid
            try:
                search_filter |= Q(qr_code_token=uuid.UUID(search))
            except (ValueError, TypeError, AttributeError):
                pass
            queryset = queryset.filter(search_filter)
        start_date, end_date = params.get("start_date"), params.get("end_date")
        if start_date or end_date:
            # A period filter is only valid when both boundaries are provided.
            from datetime import date
            from rest_framework.exceptions import ValidationError
            try:
                start, end = date.fromisoformat(start_date or ""), date.fromisoformat(end_date or "")
            except ValueError:
                raise ValidationError({"period": "Informe data inicial e final válidas."})
            if end < start:
                raise ValidationError({"period": "A data final deve ser igual ou posterior à inicial."})
            from rentals.models import RentalItem, RentalQuote
            from maintenance.models import ServiceOrder, MaintenancePlan
            from django.db.models import Exists, OuterRef
            from maintenance.services import maintenance_alert_status
            rental_conflict = RentalItem.objects.filter(
                equipment_id=OuterRef("pk"),
                quote__status__in=(RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED),
                quote__start_date__lte=end, quote__end_date__gte=start,
            )
            open_order = ServiceOrder.objects.filter(equipment_id=OuterRef("pk")).exclude(
                status__in=(ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED)
            )
            critical_plans = MaintenancePlan.objects.filter(
                equipment_id__in=queryset.values("pk"), active=True,
                criticality=MaintenancePlan.Criticality.CRITICAL,
            ).select_related("equipment")
            critical_blocked_ids = [
                plan.equipment_id for plan in critical_plans
                if maintenance_alert_status(plan) == "CRITICAL"
            ]
            queryset = queryset.annotate(
                _rental_conflict=Exists(rental_conflict),
                _open_order=Exists(open_order),
            ).exclude(
                status__in=(Equipment.Status.MAINTENANCE, Equipment.Status.INSPECTION, Equipment.Status.INACTIVE),
            ).exclude(_rental_conflict=True).exclude(_open_order=True).exclude(pk__in=critical_blocked_ids)
        ordering = params.get("ordering", "internal_code")
        allowed_ordering = {
            "name": "name", "-name": "-name", "category": "category__name",
            "code": "internal_code", "-code": "-internal_code",
            "created": "created_at", "-created": "-created_at",
            "status": "status", "-status": "-status",
            "brand": "brand", "model": "model", "daily_rate": "daily_rate", "-daily_rate": "-daily_rate",
        }
        if ordering in {"usage", "-usage"}:
            queryset = queryset.annotate(_rental_count=Count("rental_items", distinct=True)).order_by("-_rental_count" if ordering == "usage" else "_rental_count", "pk")
        elif ordering in {"rentals", "-rentals"}:
            queryset = queryset.annotate(_rental_count=Count("rental_items", distinct=True)).order_by("-_rental_count" if ordering == "rentals" else "_rental_count", "pk")
        elif ordering in allowed_ordering:
            queryset = queryset.order_by(allowed_ordering[ordering], "pk")
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

    @action(detail=True, methods=["get"], url_path="content")
    def content(self, request, pk=None):
        asset = self.get_object()
        if not asset.file:
            return Response({"detail": "Arquivo não encontrado."}, status=404)
        filename = Path(asset.file.name).name
        extension = Path(filename).suffix.lower()
        inline_types = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        try:
            stream = asset.file.open("rb")
        except (FileNotFoundError, OSError):
            return Response({"detail": "O arquivo não está disponível no armazenamento."}, status=404)
        response = FileResponse(stream, as_attachment=request.query_params.get("download") == "1" or extension not in inline_types,
                                filename=filename, content_type=inline_types.get(extension, "application/octet-stream"))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def get_queryset(self):
        queryset = super().get_queryset()
        for param, field in (("category", "category"), ("equipment", "equipment_id"), ("service_order", "service_order_id"), ("rental_quote", "rental_quote_id"), ("rental_inspection", "rental_inspection_id")):
            value = self.request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset
