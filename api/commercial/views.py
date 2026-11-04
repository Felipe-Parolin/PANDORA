from datetime import timedelta
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.db.models.functions import Coalesce, TruncDay, TruncWeek, TruncMonth, TruncYear
from django.utils import timezone
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from accounts.permissions import ACLPermission
from assets.models import Equipment
from customers.models import Customer
from maintenance.models import ServiceOrder
from rentals.models import RentalQuote, RentalItem
from core.models import AuditLog
from .models import PurchaseRecommendation, MarketingCampaign
from .serializers import PurchaseRecommendationSerializer, MarketingCampaignSerializer


def render_campaign_html(campaign, unsubscribe_url):
    from html import escape
    return (
        '<!doctype html><html><body style="margin:0;padding:24px;background:#f4f4f2;font-family:Arial,sans-serif;color:#252a32">'
        '<div style="max-width:640px;margin:0 auto;background:#fff;border:1px solid #e7e7e4;border-radius:12px;overflow:hidden">'
        '<div style="padding:22px 28px;background:#252a32;color:#fff;font-size:22px;font-weight:700;letter-spacing:2px">MAZZI</div>'
        f'<main style="padding:28px;line-height:1.6">{campaign.body_html}</main>'
        f'<footer style="padding:18px 28px;border-top:1px solid #eee;color:#777;font-size:12px">{escape(campaign.title)} · '
        f'<a href="{escape(unsubscribe_url, quote=True)}" style="color:#916000">Cancelar recebimento</a></footer>'
        '</div></body></html>'
    )

def suggest_models_to_buy(category_id, quote_items, orders_qs, lost_items, limit=3):
    """Modelos da categoria que mais merecem reforço: mais locados, mais parados em manutenção e menos disponíveis.

    Equipamentos com mesmo nome/marca/modelo são agrupados (são "o mesmo item" para efeito de compra).
    Sem nenhum equipamento na categoria, usa o que os clientes pediram e não havia.
    """
    rentals_by_eq = {r["equipment_id"]: r["n"] for r in quote_items.order_by().values("equipment_id").annotate(n=Count("quote_id", distinct=True))}
    orders_by_eq = {r["equipment_id"]: r["n"] for r in orders_qs.order_by().values("equipment_id").annotate(n=Count("id"))}
    groups = {}
    for eq in Equipment.objects.filter(category_id=category_id).exclude(status=Equipment.Status.INACTIVE):
        key = (eq.name.strip().lower(), eq.brand.strip().lower(), eq.model.strip().lower())
        g = groups.setdefault(key, {"name": eq.name.strip(), "brand": eq.brand.strip(), "model": eq.model.strip(), "units": 0,
                                    "available": 0, "rentals_90d": 0, "service_orders_90d": 0, "_rates": []})
        g["units"] += 1
        g["available"] += 1 if eq.status == Equipment.Status.AVAILABLE else 0
        g["rentals_90d"] += rentals_by_eq.get(eq.pk, 0)
        g["service_orders_90d"] += orders_by_eq.get(eq.pk, 0)
        g["_rates"].append(float(eq.daily_rate))
    ranked = sorted(groups.values(), key=lambda g: (-g["rentals_90d"], -g["service_orders_90d"], g["available"], g["name"].lower()))
    result = []
    for g in ranked[:limit]:
        rates = g.pop("_rates")
        g["avg_daily_rate"] = round(sum(rates) / len(rates), 2) if rates else None
        g["source"] = "catalog"
        result.append(g)
    if not result:
        result = [{"name": item, "brand": "", "model": "", "units": 0, "available": 0, "rentals_90d": 0,
                   "service_orders_90d": 0, "avg_daily_rate": None, "source": "requested"} for item in lost_items[:limit]]
    return result


class PurchaseRecommendationViewSet(ModelViewSet):
    queryset = PurchaseRecommendation.objects.select_related("category", "decided_by")
    serializer_class = PurchaseRecommendationSerializer
    permission_classes = [ACLPermission]
    acl_view = "assets.view"
    acl_manage = "assets.manage"

    @action(detail=False, methods=["post"], url_path="analyze")
    def analyze(self, request):
        """Evidence-based category recommendations using the last 90 days."""
        since = timezone.localdate() - timedelta(days=90)
        created = []
        categories = list(Equipment.objects.values("category_id", "category__name").annotate(total=Count("id")))
        # Pedidos não atendidos (ruptura) também geram sugestão, mesmo para categorias que a empresa ainda não possui.
        from ai.models import UnfulfilledDemand
        lost_qs = UnfulfilledDemand.objects.filter(requested_at__gte=since)
        known_ids = {row["category_id"] for row in categories}
        lost_category_ids = set(lost_qs.exclude(category__isnull=True).values_list("category_id", flat=True))
        lost_category_ids |= set(lost_qs.filter(category__isnull=True, equipment__isnull=False).values_list("equipment__category_id", flat=True))
        if lost_category_ids - known_ids:
            from assets.models import EquipmentCategory
            for extra in EquipmentCategory.objects.filter(pk__in=lost_category_ids - known_ids):
                categories.append({"category_id": extra.pk, "category__name": extra.name, "total": 0})
        for row in categories:
            category_id = row["category_id"]
            lost_rows = list(lost_qs.filter(Q(category_id=category_id) | Q(category__isnull=True, equipment__category_id=category_id)).select_related("equipment"))
            lost_requests = len(lost_rows)
            lost_units = sum(item.quantity for item in lost_rows)
            lost_customers = len({item.customer_id or f"anon-{item.pk}" for item in lost_rows})
            lost_revenue = 0.0
            lost_rate_known = 0
            for item in lost_rows:
                rate = item.expected_daily_rate if item.expected_daily_rate is not None else (item.equipment.daily_rate if item.equipment_id else None)
                if rate is not None:
                    lost_revenue += float(rate) * item.requested_days * item.quantity
                    lost_rate_known += 1
            lost_by_reason = {}
            for item in lost_rows:
                lost_by_reason[item.get_reason_display()] = lost_by_reason.get(item.get_reason_display(), 0) + item.quantity
            lost_items = sorted({item.requested_item.strip() for item in lost_rows if item.requested_item.strip()})
            assets = Equipment.objects.filter(category_id=category_id)
            available = assets.filter(status=Equipment.Status.AVAILABLE).count()
            rented = assets.filter(status=Equipment.Status.RENTED).count()
            unavailable = assets.exclude(status=Equipment.Status.AVAILABLE).count()
            orders_qs = ServiceOrder.objects.filter(equipment__category_id=category_id, opened_at__date__gte=since).exclude(
                status=ServiceOrder.Status.CANCELLED
            )
            orders = orders_qs.count()
            completed = orders_qs.filter(closed_at__isnull=False)
            downtime_hours = 0.0
            for opened, closed in completed.values_list("opened_at", "closed_at"):
                if opened and closed and closed >= opened:
                    downtime_hours += (closed - opened).total_seconds() / 3600
            open_orders = orders_qs.exclude(status=ServiceOrder.Status.COMPLETED).count()
            recurrent_equipment = orders_qs.values("equipment_id").annotate(total_orders=Count("id")).filter(total_orders__gte=2).count()
            monthly_rows = list(
                RentalItem.objects.filter(equipment__category_id=category_id, quote__created_at__date__gte=since)
                .exclude(quote__status__in=(RentalQuote.Status.CANCELLED, RentalQuote.Status.EXPIRED))
                .annotate(month=TruncMonth("quote__created_at")).values("month").annotate(requests=Count("quote_id", distinct=True)).order_by("month")
            )
            monthly_demand = [{"month": item["month"].strftime("%Y-%m"), "requests": item["requests"]} for item in monthly_rows]
            quote_items = RentalItem.objects.filter(
                equipment__category_id=category_id, quote__created_at__date__gte=since
            ).exclude(quote__status__in=(RentalQuote.Status.CANCELLED, RentalQuote.Status.EXPIRED))
            demand = quote_items.values("quote_id").distinct().count()
            requested_units = quote_items.count()
            utilization = round((rented / row["total"] * 100), 1) if row["total"] else 0
            unavailable_events = orders_qs.count() + assets.filter(status__in=(Equipment.Status.MAINTENANCE, Equipment.Status.INSPECTION)).count()
            avg_downtime = round(downtime_hours / max(1, completed.count()), 1) if completed.exists() else 0
            reasons = []
            if available == 0 and row["total"] > 0: reasons.append("Nenhuma unidade está marcada como disponível no momento.")
            if utilization >= 75: reasons.append(f"Ocupação atual de {utilization}% do parque.")
            if open_orders >= 3: reasons.append(f"{open_orders} ordens de serviço ainda não concluídas na janela.")
            if demand >= 5 and available <= max(1, row["total"] * .25): reasons.append(f"{demand} locações distintas e {requested_units} itens solicitados em 90 dias.")
            if avg_downtime >= 24: reasons.append(f"Tempo médio de indisponibilidade por OS concluída: {avg_downtime:.1f} horas.")
            if recurrent_equipment: reasons.append(f"{recurrent_equipment} equipamento(s) tiveram duas ou mais ordens de serviço no período.")
            if lost_requests:
                text = f"Ruptura: {lost_requests} pedido(s) de cliente não atendido(s) em 90 dias, somando {lost_units} unidade(s)"
                if lost_revenue:
                    text += f" e cerca de R$ {lost_revenue:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " em receita perdida registrada"
                reasons.append(text + ".")
            if not reasons: continue
            priority = "HIGH" if (available == 0 and row["total"] > 0) or open_orders >= 5 or utilization >= 90 or lost_requests >= 3 or lost_units >= 4 else "MEDIUM"
            suggested = max(1, min(10, max(demand // 5, lost_units) or 1))
            evidence = {
                "window_days": 90, "as_of": str(timezone.localdate()), "rented": rented,
                "unavailable": unavailable, "utilization_percent": utilization,
                "open_service_orders": open_orders, "service_orders_total": orders,
                "completed_service_orders": completed.count(), "downtime_hours": round(downtime_hours, 1),
                "average_downtime_hours": avg_downtime, "unavailable_events": unavailable_events,
                "equipment_with_recurrent_service": recurrent_equipment, "monthly_demand": monthly_demand,
                "distinct_rentals": demand, "requested_equipment_items": requested_units,
                "lost_requests": lost_requests, "lost_units": lost_units, "lost_customers": lost_customers,
                "lost_revenue": round(lost_revenue, 2), "lost_by_reason": lost_by_reason, "lost_requested_items": lost_items[:10],
                "lost_missing_rates": lost_requests - lost_rate_known,
                "suggested_equipment": suggest_models_to_buy(category_id, quote_items, orders_qs, lost_items),
                "limitations": "Demanda considera itens em orçamentos/locações não cancelados e os pedidos não atendidos registrados pela equipe comercial; pedidos recusados que ninguém registrou não entram na conta."
            }
            rec, was_created = PurchaseRecommendation.objects.get_or_create(
                category_id=category_id, status=PurchaseRecommendation.Status.PENDING,
                defaults={"current_total": row["total"], "current_available": available, "demand_events": demand,
                          "maintenance_orders": orders, "unavailable_days": round(downtime_hours / 24, 2),
                          "suggested_quantity": suggested,
                          "priority": priority, "rationale": " ".join(reasons), "evidence": evidence}
            )
            if not was_created:
                rec.current_total = row["total"]
                rec.current_available = available
                rec.demand_events = demand
                rec.maintenance_orders = orders
                rec.unavailable_days = round(downtime_hours / 24, 2)
                rec.suggested_quantity = suggested
                rec.priority = priority
                rec.rationale = " ".join(reasons)
                rec.evidence = evidence
                rec.save(update_fields=("current_total", "current_available", "demand_events", "maintenance_orders", "unavailable_days", "suggested_quantity", "priority", "rationale", "evidence", "updated_at"))
            if was_created:
                created.append(rec)
        uncategorized = lost_qs.filter(category__isnull=True, equipment__isnull=True).count()
        return Response({"created": len(created), "lost_without_category": uncategorized,
                         "recommendations": self.get_serializer(created, many=True).data})

    @action(detail=True, methods=["post"], url_path="decision")
    def decision(self, request, pk=None):
        rec = self.get_object()
        new_status = request.data.get("status")
        allowed = {v for v, _ in PurchaseRecommendation.Status.choices}
        if new_status not in allowed - {PurchaseRecommendation.Status.PENDING}:
            raise ValidationError({"status": "Informe APPROVED, REJECTED ou ACQUIRED."})
        rec.status = new_status
        rec.decision_note = str(request.data.get("note", ""))[:2000]
        rec.decided_by = request.user
        rec.decided_at = timezone.now()
        rec.save()
        AuditLog.objects.create(user=request.user, entity="PurchaseRecommendation", record_id=str(rec.pk), action="DECISION", data={"status": new_status, "note": rec.decision_note})
        return Response(self.get_serializer(rec).data)

class BillingAnalyticsView(APIView):
    permission_classes = [ACLPermission]
    acl_view = "rentals.view"
    def get(self, request):
        from datetime import date, timedelta
        from rest_framework.exceptions import ValidationError
        qs = RentalQuote.objects.filter(status__in=(RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED, RentalQuote.Status.COMPLETED))
        start_raw, end_raw = request.query_params.get("start_date"), request.query_params.get("end_date")
        try:
            start = date.fromisoformat(start_raw) if start_raw else None
            end = date.fromisoformat(end_raw) if end_raw else None
        except ValueError:
            raise ValidationError({"period": "Informe datas no formato AAAA-MM-DD."})
        if start and end and end < start:
            raise ValidationError({"period": "A data final deve ser igual ou posterior à inicial."})
        if start: qs = qs.filter(Q(delivered_at__date__gte=start) | Q(delivered_at__isnull=True, created_at__date__gte=start))
        if end: qs = qs.filter(Q(delivered_at__date__lte=end) | Q(delivered_at__isnull=True, created_at__date__lte=end))
        customer_filter = request.query_params.get("customer", "").strip()
        if customer_filter:
            qs = qs.filter(customer_id=customer_filter) if customer_filter.isdigit() else qs.filter(customer__name__icontains=customer_filter)
        if request.query_params.get("category"): qs = qs.filter(items__equipment__category_id=request.query_params["category"])
        equipment_filter = request.query_params.get("equipment", "").strip()
        if equipment_filter:
            qs = qs.filter(items__equipment_id=equipment_filter) if equipment_filter.isdigit() else qs.filter(Q(items__equipment__name__icontains=equipment_filter) | Q(items__equipment__internal_code__icontains=equipment_filter))
        filtered_ids = qs.values("id")
        qs = RentalQuote.objects.filter(pk__in=filtered_ids, status__in=(RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED, RentalQuote.Status.COMPLETED))
        contract_rows = list(qs.values("id", "number", "customer__name", "created_at", "delivered_at", "start_date", "end_date", "status", "subtotal", "transport_fee", "discount", "total"))
        by_customer = list(qs.values("customer__name").annotate(total=Sum("total"), contracts=Count("id")).order_by("-total")[:10])
        item_qs = RentalItem.objects.filter(quote__in=qs)
        if request.query_params.get("category"):
            item_qs = item_qs.filter(equipment__category_id=request.query_params["category"])
        if equipment_filter:
            item_qs = item_qs.filter(equipment_id=equipment_filter) if equipment_filter.isdigit() else item_qs.filter(Q(equipment__name__icontains=equipment_filter) | Q(equipment__internal_code__icontains=equipment_filter))
        by_equipment = list(item_qs.values("equipment__name", "equipment__internal_code", "equipment__category__name").annotate(total=Sum("total"), rentals=Count("quote", distinct=True)).order_by("-total")[:10])
        by_category = list(item_qs.values("equipment__category__name").annotate(total=Sum("total"), rentals=Count("quote", distinct=True), items=Count("id")).order_by("-total"))
        gross = sum((r["subtotal"] + r["transport_fee"] for r in contract_rows), 0)
        freight = sum((r["transport_fee"] for r in contract_rows), 0)
        discounts = sum((r["discount"] for r in contract_rows), 0)
        net = sum((r["total"] for r in contract_rows), 0)
        granularity = request.query_params.get("group_by", "month")
        truncators = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth, "year": TruncYear}
        if granularity not in truncators:
            raise ValidationError({"group_by": "Use day, week, month ou year."})
        period_field = truncators[granularity](Coalesce("delivered_at", "created_at"))
        by_period = list(qs.annotate(period=period_field).values("period").annotate(total=Sum("total"), gross=Sum("subtotal") + Sum("transport_fee"), contracts=Count("id")).order_by("period"))
        comparison = None
        if start and end:
            span = (end - start).days + 1
            prev_start, prev_end = start - timedelta(days=span), start - timedelta(days=1)
            prev = RentalQuote.objects.filter(status__in=(RentalQuote.Status.ACTIVE, RentalQuote.Status.RETURNED, RentalQuote.Status.COMPLETED)).filter(
                Q(delivered_at__date__gte=prev_start, delivered_at__date__lte=prev_end) |
                Q(delivered_at__isnull=True, created_at__date__gte=prev_start, created_at__date__lte=prev_end)
            )
            if customer_filter:
                prev = prev.filter(customer_id=customer_filter) if customer_filter.isdigit() else prev.filter(customer__name__icontains=customer_filter)
            if request.query_params.get("category"): prev = prev.filter(items__equipment__category_id=request.query_params["category"])
            if equipment_filter:
                prev = prev.filter(items__equipment_id=equipment_filter) if equipment_filter.isdigit() else prev.filter(Q(items__equipment__name__icontains=equipment_filter) | Q(items__equipment__internal_code__icontains=equipment_filter))
            previous_total = RentalQuote.objects.filter(pk__in=prev.values("id")).aggregate(value=Sum("total"))["value"] or 0
            delta = net - previous_total
            comparison = {"start_date": prev_start, "end_date": prev_end, "previous_net": previous_total,
                          "difference": delta, "percent_change": round(float(delta / previous_total * 100), 2) if previous_total else None}
        return Response({"period": {"start_date": start_raw, "end_date": end_raw, "group_by": granularity},
                         "count": len(contract_rows), "active_contracts": qs.filter(status=RentalQuote.Status.ACTIVE).count(),
                         "average_ticket": net / len(contract_rows) if contract_rows else 0,
                         "gross": gross, "freight": freight, "discounts": discounts,
                         "net": net, "by_period": by_period, "by_customer": by_customer,
                         "top_equipment": by_equipment, "by_category": by_category,
                         "contracts": contract_rows, "comparison": comparison,
                         "revenue_basis": "Receita contratual gerencial de locações ACTIVE, RETURNED e COMPLETED. Não representa recebimento de caixa, conciliação bancária ou faturamento fiscal; orçamentos cancelados, expirados, rascunhos e enviados ficam fora.",
                         "filter_basis": "Os filtros de categoria/equipamento selecionam contratos que contêm itens correspondentes; os indicadores financeiros e a tabela de contratos mostram o valor integral desses contratos. Os rankings por equipamento/categoria consideram apenas os itens filtrados."})

class MarketingCampaignViewSet(ModelViewSet):
    queryset = MarketingCampaign.objects.select_related("created_by")
    serializer_class = MarketingCampaignSerializer
    permission_classes = [ACLPermission]
    acl_view = "customers.view"
    acl_manage = "customers.manage"
    def perform_create(self, serializer): serializer.save(created_by=self.request.user)
    @action(detail=True, methods=["post"], url_path="prepare")
    def prepare(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in {MarketingCampaign.Status.DRAFT, MarketingCampaign.Status.FAILED}:
            raise ValidationError("Somente rascunhos ou campanhas sem envios podem ser preparados novamente.")
        requested_ids = request.data.get("customer_ids")
        eligible = Customer.objects.filter(is_active=True, marketing_opt_in=True).exclude(email="")
        if requested_ids is not None:
            if not isinstance(requested_ids, list) or not requested_ids:
                raise ValidationError({"customer_ids": "Selecione ao menos um destinatário autorizado."})
            recipients = list(eligible.filter(pk__in=requested_ids).values_list("id", flat=True))
            if len(recipients) != len(set(requested_ids)):
                raise ValidationError({"customer_ids": "Um ou mais clientes não existem, estão inativos ou não autorizaram marketing."})
        else:
            recipients = list(eligible.values_list("id", flat=True))
        if not recipients:
            raise ValidationError("Nenhum cliente ativo com e-mail e autorização de marketing.")
        campaign.status = MarketingCampaign.Status.READY
        campaign.recipient_count = len(recipients)
        campaign.result_log = [{"prepared_customer_ids": recipients, "sent": False, "reason": "Lista preparada; envio exige ação explícita."}]
        campaign.save(update_fields=("status", "recipient_count", "result_log"))
        return Response(self.get_serializer(campaign).data)
    @transaction.atomic
    @action(detail=True, methods=["post"], url_path="send")
    def send(self, request, pk=None):
        campaign = MarketingCampaign.objects.select_for_update().get(pk=self.get_object().pk)
        if campaign.status != MarketingCampaign.Status.READY:
            raise ValidationError("Prepare a campanha e confira os destinatários antes do envio.")
        if campaign.scheduled_at and campaign.scheduled_at > timezone.now():
            raise ValidationError({"scheduled_at": "A campanha está programada para uma data futura; o comando agendador fará o envio no horário definido."})
        if not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL:
            raise ValidationError("Configure EMAIL_HOST e DEFAULT_FROM_EMAIL no ambiente antes do envio.")
        prepared_ids = campaign.result_log[0].get("prepared_customer_ids", []) if campaign.result_log else []
        recipients = Customer.objects.filter(pk__in=prepared_ids, is_active=True, marketing_opt_in=True).exclude(email="")
        logs, sent = [], 0
        for customer in recipients.iterator():
            unsubscribe = request.build_absolute_uri(f"/api/marketing/unsubscribe/{customer.marketing_unsubscribe_token}/")
            html = render_campaign_html(campaign, unsubscribe)
            message = EmailMultiAlternatives(campaign.subject, strip_tags(html), settings.DEFAULT_FROM_EMAIL, [customer.email])
            message.attach_alternative(html, "text/html")
            try:
                message.send(fail_silently=False)
                sent += 1
                logs.append({"customer_id": customer.pk, "email": customer.email, "sent": True})
            except Exception as exc:
                logs.append({"customer_id": customer.pk, "email": customer.email, "sent": False, "error": str(exc)[:300]})
        campaign.recipient_count = len(logs)
        campaign.result_log = logs
        campaign.status = (MarketingCampaign.Status.SENT if sent == len(logs) and sent else
                           MarketingCampaign.Status.PARTIAL if sent else MarketingCampaign.Status.FAILED)
        campaign.sent_at = timezone.now() if sent else None
        campaign.save(update_fields=("recipient_count", "result_log", "status", "sent_at"))
        return Response({"sent": sent, "failed": len(logs) - sent, "campaign": self.get_serializer(campaign).data})

class MarketingUnsubscribeView(APIView):
    permission_classes = []
    authentication_classes = []
    def get(self, request, token):
        from django.shortcuts import get_object_or_404
        customer = get_object_or_404(Customer, marketing_unsubscribe_token=token)
        if customer.marketing_opt_in:
            customer.marketing_opt_in = False
            customer.save(update_fields=("marketing_opt_in",))
        return Response({"detail": "Descadastramento realizado. Este endereço não receberá novas campanhas comerciais."})

