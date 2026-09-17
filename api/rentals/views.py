from datetime import date
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import ACLPermission
from assets.models import Equipment
from assets.serializers import EquipmentSerializer
from .models import RentalQuote
from .serializers import RentalQuoteSerializer
from .services import availability_reason


class RentalQuoteViewSet(ModelViewSet):
    queryset = RentalQuote.objects.select_related("customer", "created_by").prefetch_related("items__equipment")
    serializer_class = RentalQuoteSerializer
    permission_classes = [ACLPermission]
    acl_view = "rentals.view"
    acl_manage = "rentals.manage"

    def get_queryset(self):
        queryset = super().get_queryset()
        for key, field in (("status", "status"), ("customer", "customer_id")):
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    @action(detail=False, methods=["get"])
    def availability(self, request):
        try:
            start = date.fromisoformat(request.query_params["start"])
            end = date.fromisoformat(request.query_params["end"])
        except (KeyError, ValueError):
            return Response({"detail": "Informe start e end no formato AAAA-MM-DD."}, status=400)
        ignore_quote = None
        if request.query_params.get("ignore_quote"):
            try:
                ignore_quote = self.get_queryset().get(pk=request.query_params["ignore_quote"])
            except RentalQuote.DoesNotExist:
                return Response({"detail": "Orçamento informado para edição não foi encontrado."}, status=404)
        available, blocked = [], []
        for equipment in Equipment.objects.select_related("category"):
            reason = availability_reason(equipment, start, end, ignore_quote)
            (blocked if reason else available).append({"equipment": EquipmentSerializer(equipment).data, "reason": reason})
        return Response({"available": available, "blocked": blocked})
