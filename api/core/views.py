from django.db import connection
from django.db.models import Count, Sum
from django.db.utils import OperationalError
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from assets.models import Equipment
from customers.models import Customer
from maintenance.models import MaintenancePlan, ServiceOrder
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
        today = timezone.localdate()
        equipment_by_status = {row["status"]: row["total"] for row in Equipment.objects.values("status").annotate(total=Count("id"))}
        quotes_total = RentalQuote.objects.exclude(status=RentalQuote.Status.CANCELLED).aggregate(total=Sum("total"))["total"] or 0
        return Response({
            "customers": Customer.objects.filter(is_active=True).count(),
            "equipment": Equipment.objects.count(),
            "equipment_by_status": equipment_by_status,
            "open_orders": ServiceOrder.objects.exclude(status__in=[ServiceOrder.Status.COMPLETED, ServiceOrder.Status.CANCELLED]).count(),
            "overdue_maintenance": MaintenancePlan.objects.filter(active=True, next_due_date__lt=today).count(),
            "active_quotes": RentalQuote.objects.exclude(status__in=[RentalQuote.Status.CANCELLED, RentalQuote.Status.EXPIRED]).count(),
            "quotes_total": quotes_total,
            "recent_quotes": list(RentalQuote.objects.select_related("customer").values("id", "number", "customer__name", "status", "total", "created_at")[:5]),
        })
