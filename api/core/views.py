from django.db import connection
from django.db.models import Count, Sum
from django.db.utils import OperationalError
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import DestroyModelMixin, ListModelMixin
from rest_framework.decorators import action
from django.utils import timezone

from assets.models import Equipment
from customers.models import Customer
from maintenance.models import MaintenancePlan, ServiceOrder
from maintenance.services import maintenance_alert_status
from rentals.models import RentalQuote
from accounts.permissions import ACLPermission
from .models import Notification
from .serializers import NotificationSerializer


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except OperationalError:
            return Response({"status": "error", "service": "pandora-api", "database": "unavailable"}, status=503)
        return Response({"status": "ok", "service": "pandora-api", "database": connection.vendor})


class DashboardView(APIView):
    permission_classes = [ACLPermission]
    acl_view = "dashboard.view"

    def get(self, request):
        from datetime import date
        from django.db.models import Q
        from rentals.models import RentalInspection
        from logistics.models import TransportTask

        today = timezone.localdate()
        equipment_by_status = {
            row["status"]: row["total"]
            for row in Equipment.objects.values("status").annotate(total=Count("id"))
        }
        active_statuses = (
            RentalQuote.Status.DRAFT, RentalQuote.Status.SENT, RentalQuote.Status.APPROVED,
            RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED,
        )
        realized_statuses = (
            RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED, RentalQuote.Status.COMPLETED,
        )
        quote_queryset = RentalQuote.objects.all()
        revenue_queryset = RentalQuote.objects.filter(status__in=realized_statuses)
        start_raw, end_raw = request.query_params.get("start_date"), request.query_params.get("end_date")
        if start_raw or end_raw:
            try:
                start_date = date.fromisoformat(start_raw) if start_raw else date.min
                end_date = date.fromisoformat(end_raw) if end_raw else date.max
            except ValueError:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"period": "Informe datas no formato AAAA-MM-DD."})
            if end_date < start_date:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"period": "A data final deve ser igual ou posterior à inicial."})
            revenue_queryset = revenue_queryset.filter(
                Q(delivered_at__date__gte=start_date, delivered_at__date__lte=end_date)
                | Q(delivered_at__isnull=True, created_at__date__gte=start_date, created_at__date__lte=end_date)
            )

        maintenance_statuses = [
            maintenance_alert_status(plan)
            for plan in MaintenancePlan.objects.filter(active=True).select_related("equipment")
        ]
        open_orders = ServiceOrder.objects.exclude(
            status__in=[ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED]
        )
        pending_inspections = RentalInspection.objects.filter(result=RentalInspection.Result.PENDING)
        transport_today = TransportTask.objects.filter(scheduled_at__date=today).exclude(
            status=TransportTask.Status.CANCELLED
        )
        overdue_rentals = RentalQuote.objects.filter(
            status=RentalQuote.Status.ACTIVE, items__stage="DELIVERED", items__end_date__lt=today
        ).distinct().count()
        from datetime import timedelta
        agenda_end = today + timedelta(days=7)
        agenda_tasks = list(TransportTask.objects.filter(
            scheduled_at__date__gte=today, scheduled_at__date__lte=agenda_end
        ).exclude(status=TransportTask.Status.CANCELLED).select_related(
            "quote__customer", "vehicle", "driver"
        ).order_by("scheduled_at")[:30].values(
            "id", "leg", "status", "scheduled_at", "address",
            "quote__number", "quote__customer__name", "vehicle__plate", "driver__full_name"
        ))
        maintenance_due_today = MaintenancePlan.objects.filter(active=True, next_due_date__lte=today).count()
        upcoming_maintenance = MaintenancePlan.objects.filter(
            active=True, next_due_date__gt=today, next_due_date__lte=today + timedelta(days=15)
        ).count()
        waiting_release = ServiceOrder.objects.filter(
            status=ServiceOrder.Status.COMPLETED, released=False
        ).count()
        blocked_inspections = RentalInspection.objects.filter(result=RentalInspection.Result.BLOCKED).count()
        overdue_collections = TransportTask.objects.filter(
            leg=TransportTask.Leg.RETURN, scheduled_at__date__lt=today
        ).exclude(status__in=(TransportTask.Status.COMPLETED, TransportTask.Status.CANCELLED)).count()
        revenue_total = revenue_queryset.aggregate(total=Sum("total"))["total"] or 0
        by_status = {key: equipment_by_status.get(key, 0) for key in (
            Equipment.Status.AVAILABLE, Equipment.Status.RESERVED, Equipment.Status.RENTED,
            Equipment.Status.MAINTENANCE, Equipment.Status.INSPECTION, Equipment.Status.INACTIVE,
        )}
        payload = {
            "customers": Customer.objects.filter(is_active=True).count(),
            "equipment": Equipment.objects.count(),
            "equipment_by_status": equipment_by_status,
            "available_equipment": by_status[Equipment.Status.AVAILABLE],
            "rented_equipment": by_status[Equipment.Status.RENTED],
            "reserved_equipment": by_status[Equipment.Status.RESERVED],
            "maintenance_equipment": by_status[Equipment.Status.MAINTENANCE],
            "blocked_equipment": by_status[Equipment.Status.INSPECTION] + by_status[Equipment.Status.INACTIVE],
            "open_orders": open_orders.count(),
            "orders_in_progress": open_orders.filter(status=ServiceOrder.Status.IN_PROGRESS).count(),
            "orders_waiting": open_orders.filter(status__in=(ServiceOrder.Status.OPEN, ServiceOrder.Status.SCHEDULED, ServiceOrder.Status.WAITING_PARTS)).count(),
            "orders_open_count": open_orders.filter(status=ServiceOrder.Status.OPEN).count(),
            "orders_waiting_parts": open_orders.filter(status=ServiceOrder.Status.WAITING_PARTS).count(),
            "maintenance_due_today": maintenance_due_today,
            "upcoming_maintenance": upcoming_maintenance,
            "waiting_technical_release": waiting_release,
            "blocked_inspections": blocked_inspections,
            "overdue_maintenance": sum(item in {"OVERDUE", "CRITICAL"} for item in maintenance_statuses),
            "maintenance_alerts": {key: maintenance_statuses.count(key) for key in ("UPCOMING", "OVERDUE", "CRITICAL")},
            "pending_inspections": pending_inspections.count(),
            "rentals_in_progress": quote_queryset.filter(status=RentalQuote.Status.ACTIVE).count(),
            "conversion_percent": round(100 * quote_queryset.filter(status__in=(RentalQuote.Status.APPROVED, *realized_statuses)).count() / max(quote_queryset.count(), 1)),
            "active_quotes": quote_queryset.filter(status__in=active_statuses).count(),
            "quotes_waiting_approval": quote_queryset.filter(status__in=(RentalQuote.Status.DRAFT, RentalQuote.Status.SENT)).count(),
            "quotes_total": quote_queryset.filter(status__in=active_statuses).aggregate(total=Sum("total"))["total"] or 0,
            "realized_revenue": revenue_total,
            "deliveries_today": transport_today.filter(leg=TransportTask.Leg.DELIVERY).count(),
            "collections_today": transport_today.filter(leg=TransportTask.Leg.RETURN).count(),
            "overdue_rentals": overdue_rentals,
            "overdue_collections": overdue_collections,
            "agenda_next_7_days": agenda_tasks,
            "recent_quotes": list(RentalQuote.objects.select_related("customer").values(
                "id", "number", "customer__name", "status", "total", "created_at"
            )[:10]),
            "revenue_period": {"start_date": start_raw, "end_date": end_raw, "total": revenue_total},
        }
        domain_fields = {
            "assets.view": {"equipment", "equipment_by_status", "available_equipment", "rented_equipment", "reserved_equipment", "maintenance_equipment", "blocked_equipment"},
            "customers.view": {"customers"},
            "maintenance.view": {"open_orders", "orders_in_progress", "orders_waiting", "orders_open_count", "orders_waiting_parts", "maintenance_due_today", "upcoming_maintenance", "waiting_technical_release", "blocked_inspections", "overdue_maintenance", "maintenance_alerts", "pending_inspections"},
            "rentals.view": {"active_quotes", "quotes_waiting_approval", "quotes_total", "realized_revenue", "recent_quotes", "revenue_period", "overdue_rentals", "pending_inspections", "blocked_inspections", "rentals_in_progress", "conversion_percent"},
            "logistics.view": {"deliveries_today", "collections_today", "overdue_collections", "agenda_next_7_days"},
        }
        allowed = set().union(*(fields for permission, fields in domain_fields.items() if request.user.has_acl(permission)))
        return Response({key: value for key, value in payload.items() if key in allowed})




class NotificationViewSet(ListModelMixin, DestroyModelMixin, GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ("get", "post", "delete", "head", "options")

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        unread_count = queryset.filter(read_at__isnull=True).count()
        listed = queryset.filter(read_at__isnull=True) if request.query_params.get("status") == "unread" else queryset
        kind = request.query_params.get("kind")
        if kind:
            from rest_framework.exceptions import ValidationError
            if kind not in Notification.Kind.values:
                raise ValidationError({"kind": "Selecione um assunto válido para as notificações."})
            listed = listed.filter(kind=kind)
        try:
            page = int(request.query_params.get("page", 1))
            if page < 1:
                raise ValueError
        except (TypeError, ValueError):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"page": "Informe uma página válida."})
        count = listed.count()
        notifications = listed.order_by("-created_at", "-pk")[(page - 1) * 30:page * 30]
        counts = {row["kind"]: row["count"] for row in queryset.values("kind").annotate(count=Count("id"))}
        return Response({
            "unread_count": unread_count, "counts": counts, "count": count,
            "next_page": page + 1 if page * 30 < count else None,
            "results": self.get_serializer(notifications, many=True).data,
        })

    @action(detail=True, methods=["post"], url_path="read")
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.read_at:
            notification.read_at = timezone.now()
            notification.save(update_fields=("read_at",))
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        count = self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"marked_read": count})
