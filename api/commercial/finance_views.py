from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from accounts.permissions import ACLPermission
from core.models import AuditLog
from core.tax_ids import normalize_tax_id
from customers.models import Customer
from .finance_serializers import ReceivableSerializer, PaymentSerializer, SettlementPreviewSerializer, SettlementSerializer
from .models import Receivable, Payment
from .receivables import charges, payment_preview, settle


class FinancePagination(PageNumberPagination):
    page_size = 10


class ReceivableViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Receivable.objects.select_related("customer", "quote", "allocation__payment")
    serializer_class = ReceivableSerializer
    permission_classes = [ACLPermission]
    acl_view = "commercial.receivables.view"
    acl_manage = "commercial.receivables.manage"
    pagination_class = FinancePagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("customer"):
            if not params["customer"].isdigit():
                raise ValidationError({"customer": "Informe um cliente válido."})
            qs = qs.filter(customer_id=params["customer"])
        if params.get("status"):
            if params["status"] not in Receivable.Status.values:
                raise ValidationError({"status": "Situação inválida."})
            qs = qs.filter(status=params["status"])
        search = params.get("search", "").strip()
        if search:
            query = Q(description__icontains=search) | Q(quote__number__icontains=search) | Q(customer__name__icontains=search)
            numeric = search.upper().removeprefix("CR-")
            if numeric.isdigit() and len(numeric) < 19:
                query |= Q(pk=int(numeric))
            qs = qs.filter(query)
        order = params.get("ordering", "due_date")
        if order not in {"due_date", "-due_date", "issue_date", "-issue_date", "amount", "-amount", "-allocation__payment__payment_date"}:
            order = "due_date"
        return qs.order_by(order, "pk")

    @transaction.atomic
    def perform_create(self, serializer):
        Customer.objects.select_for_update().get(pk=serializer.validated_data["customer"].pk)
        title = serializer.save(created_by=self.request.user)
        AuditLog.objects.create(user=self.request.user, entity="Receivable", record_id=title.pk, action="created", data={"amount": str(title.amount), "due_date": str(title.due_date)})

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        initial = self.get_object()
        Customer.objects.select_for_update().get(pk=initial.customer_id)
        instance = Receivable.objects.select_for_update().get(pk=initial.pk)
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        previous = {key: str(getattr(instance, key)) for key in serializer.validated_data}
        serializer.save()
        AuditLog.objects.create(user=request.user, entity="Receivable", record_id=instance.pk, action="updated", data={"previous": previous, "current": {key: str(getattr(instance, key)) for key in serializer.validated_data}})
        return Response(self.get_serializer(self.get_queryset().get(pk=instance.pk)).data)

    @action(detail=False, methods=["get"])
    def customers(self, request):
        params = request.query_params
        qs = Customer.objects.annotate(
            title_count=Count("receivables"),
            open_count=Count("receivables", filter=Q(receivables__status="OPEN")),
            paid_count=Count("receivables", filter=Q(receivables__status="PAID")),
            billed=Sum("receivables__amount"),
            paid_principal=Sum("receivables__amount", filter=Q(receivables__status="PAID")),
            paid_interest=Sum("receivables__allocation__interest", filter=Q(receivables__status="PAID")),
            open_principal=Sum("receivables__amount", filter=Q(receivables__status="OPEN")),
        )
        if params.get("include_empty") != "true":
            qs = qs.filter(title_count__gt=0)
        if params.get("customer"):
            if not params["customer"].isdigit():
                raise ValidationError({"customer": "Informe um cliente válido."})
            qs = qs.filter(pk=params["customer"])
        if params.get("situation") == "open":
            qs = qs.filter(open_count__gt=0)
        elif params.get("situation") == "paid":
            qs = qs.filter(paid_count__gt=0)
        elif params.get("situation") == "overdue":
            qs = qs.filter(pk__in=Receivable.objects.filter(status="OPEN", due_date__lt=timezone.localdate()).values("customer_id"))
        search = params.get("search", "").strip()
        if search:
            query = Q(name__icontains=search) | Q(document__icontains=search)
            document = normalize_tax_id(search)
            if document:
                query |= Q(document__icontains=document)
            qs = qs.filter(query)
        order = params.get("ordering", "name")
        qs = qs.order_by(order if order in {"name", "-name", "-open_principal", "-paid_principal", "-billed"} else "name", "pk")
        page = self.paginate_queryset(qs)
        totals = {item.pk: {"open_total": Decimal("0"), "interest": Decimal("0"), "overdue_total": Decimal("0")} for item in page}
        for title in Receivable.objects.filter(customer_id__in=totals, status="OPEN").select_related("quote"):
            detail = charges(title, timezone.localdate())
            entry = totals[title.customer_id]
            entry["open_total"] += Decimal(detail["total"])
            entry["interest"] += Decimal(detail["interest"])
            if detail["late_days"]:
                entry["overdue_total"] += Decimal(detail["total"])
        result = [{"id": item.pk, "name": item.name, "document": item.document, "is_active": item.is_active,
                   "title_count": item.title_count, "open_count": item.open_count, "paid_count": item.paid_count,
                   "billed": str(item.billed or 0), "paid_total": str((item.paid_principal or 0) + (item.paid_interest or 0)),
                   **{key: str(value) for key, value in totals[item.pk].items()}} for item in page]
        return self.get_paginated_response(result)

    @action(detail=False, methods=["post"], url_path="settlement-preview")
    def settlement_preview(self, request):
        serializer = SettlementPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        get_object_or_404(Customer, pk=data["customer"])
        preview, _ = payment_preview(data["customer"], data["receivable_ids"], data["payment_date"])
        return Response(preview)

    @action(detail=False, methods=["post"])
    def settle(self, request):
        serializer = SettlementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        get_object_or_404(Customer, pk=serializer.validated_data["customer"])
        payment, created = settle(serializer.validated_data, request.user)
        return Response(PaymentSerializer(payment).data, status=201 if created else 200)


class PaymentViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [ACLPermission]
    acl_view = "commercial.receivables.view"
    pagination_class = FinancePagination

    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        from .receipt_pdf import render_receipt
        payment = self.get_object()
        response = HttpResponse(render_receipt(payment), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{payment.number}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
