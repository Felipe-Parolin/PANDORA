from django.db import connection
from django.db.models import Count, Sum
from django.db.utils import OperationalError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from assets.models import Equipment
from customers.models import Customer
from maintenance.models import MaintenancePlan, ServiceOrder
from maintenance.services import maintenance_alert_status
from rentals.models import RentalQuote
from accounts.permissions import ACLPermission


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
        equipment_by_status = {row["status"]: row["total"] for row in Equipment.objects.values("status").annotate(total=Count("id"))}
        quotes_total = RentalQuote.objects.exclude(status=RentalQuote.Status.CANCELLED).aggregate(total=Sum("total"))["total"] or 0
        maintenance_statuses = [maintenance_alert_status(plan) for plan in MaintenancePlan.objects.filter(active=True).select_related("equipment")]
        return Response({
            "customers": Customer.objects.filter(is_active=True).count(),
            "equipment": Equipment.objects.count(),
            "equipment_by_status": equipment_by_status,
            "open_orders": ServiceOrder.objects.exclude(status__in=[ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED]).count(),
            "overdue_maintenance": sum(item in {"OVERDUE", "CRITICAL"} for item in maintenance_statuses),
            "maintenance_alerts": {key: maintenance_statuses.count(key) for key in ("UPCOMING", "OVERDUE", "CRITICAL")},
            "active_quotes": RentalQuote.objects.filter(status__in=[RentalQuote.Status.DRAFT, RentalQuote.Status.SENT, RentalQuote.Status.APPROVED, RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED]).count(),
            "quotes_total": quotes_total,
            "recent_quotes": list(RentalQuote.objects.select_related("customer").values("id", "number", "customer__name", "status", "total", "created_at")[:5]),
        })
