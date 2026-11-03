from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework import status as http

from accounts.permissions import ACLPermission
from assets.models import Equipment, MediaAsset

from . import serializers as s
from .knowledge import INDEXABLE_CATEGORIES, index_media, is_indexable
from .models import AIConsultation, ManualIndex
from .reports import build_operational_report, default_period
from .risk import RiskAnalyzer
from .services import AIAssistantFacade


class AIBaseView(APIView):
    permission_classes = [ACLPermission]
    acl_view = "ai.assist"
    acl_manage = "ai.assist"
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def facade(self, request):
        return AIAssistantFacade(request.user)

    @staticmethod
    def check_equipment_access(user, equipment):
        if equipment is not None and not (user.has_acl("assets.view") or user.has_acl("maintenance.view")):
            raise PermissionDenied("Seu grupo não pode consultar este equipamento.")

    @staticmethod
    def check_order_access(user, order):
        if order is not None and not user.has_acl("maintenance.view"):
            raise PermissionDenied("Seu grupo não pode consultar ordens de serviço.")


class StatusView(AIBaseView):
    def get(self, request):
        return Response(self.facade(request).status())


class SearchView(AIBaseView):
    def post(self, request):
        data = _valid(s.SearchInputSerializer, request)
        self.check_equipment_access(request.user, data.get("equipment"))
        self.check_order_access(request.user, data.get("service_order"))
        result = self.facade(request).search(data["query"], data.get("equipment"), data.get("service_order"), data["input_source"])
        return Response(result)


class DiagnoseView(AIBaseView):
    def post(self, request):
        data = _valid(s.DiagnoseInputSerializer, request)
        self.check_equipment_access(request.user, data["equipment"])
        self.check_order_access(request.user, data.get("service_order"))
        result = self.facade(request).diagnose(
            data["symptoms"], data["equipment"], data.get("service_order"), data["input_source"], data["transcription_confirmed"]
        )
        return Response(result)


class AskView(AIBaseView):
    def post(self, request):
        data = _valid(s.AskInputSerializer, request)
        self.check_equipment_access(request.user, data.get("equipment"))
        return Response(self.facade(request).ask(data["question"], data.get("equipment")))


class TranscribeView(AIBaseView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        data = _valid(s.TranscribeInputSerializer, request)
        return Response(self.facade(request).transcribe(data["audio"]))


class ExtractReportView(AIBaseView):
    def post(self, request):
        data = _valid(s.ExtractInputSerializer, request)
        self.check_equipment_access(request.user, data.get("equipment"))
        return Response(self.facade(request).extract_report(
            data["text"], data["input_source"], data["transcription_confirmed"], data.get("equipment"), data.get("maintenance_type", ""),
        ))


class ConsultationViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    serializer_class = s.AIConsultationSerializer
    permission_classes = [ACLPermission]
    acl_view = "ai.assist"
    acl_manage = "ai.assist"
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai"

    def get_queryset(self):
        queryset = AIConsultation.objects.select_related("user", "equipment", "service_order").prefetch_related("decisions__decided_by")
        if not self.request.user.has_acl("ai.audit"):
            queryset = queryset.filter(user=self.request.user)
        for param in ("service_order", "equipment", "kind", "status"):
            value = self.request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{param if param in ("kind", "status") else f"{param}_id": value})
        return queryset

    @action(detail=True, methods=["post"])
    def decision(self, request, pk=None):
        consultation = self.get_object()
        data = _valid(s.DecisionInputSerializer, request)
        record = AIAssistantFacade(request.user).decide(
            consultation, data["decision"], data["reason"], data["final_text"], data["apply_to_order"], data["final_tests"], data["parts_used"])
        return Response(s.AIDecisionSerializer(record).data, status=http.HTTP_201_CREATED)


class RecurrenceView(APIView):
    permission_classes = [ACLPermission]
    acl_view = ("dashboard.view", "maintenance.view", "ai.assist")

    def get(self, request, equipment_id=None):
        analyzer = RiskAnalyzer()
        if equipment_id is not None:
            equipment = Equipment.objects.filter(pk=equipment_id).first()
            if equipment is None:
                return Response({"detail": "Equipamento não encontrado."}, status=404)
            return Response(analyzer.assess(equipment).__dict__)
        limit = min(int(request.query_params.get("limit", 10) or 10), 50)
        return Response({"results": [item.__dict__ for item in analyzer.ranking(limit=limit)]})


class OperationalReportView(APIView):
    permission_classes = [ACLPermission]
    acl_view = "dashboard.view"

    def get(self, request):
        data = _valid(s.ReportPeriodSerializer, request, query=True)
        default_start, default_end = default_period()
        return Response(build_operational_report(data.get("start", default_start), data.get("end", default_end)))


class ReportSummaryView(AIBaseView):
    """Resumo em linguagem natural; só recebe números agregados (sem dados pessoais)."""

    def post(self, request):
        data = _valid(s.ReportPeriodSerializer, request)
        if not request.user.has_acl("dashboard.view"):
            raise PermissionDenied("Seu grupo não pode consultar relatórios.")
        default_start, default_end = default_period()
        report = build_operational_report(data.get("start", default_start), data.get("end", default_end))
        return Response({"report": report, **self.facade(request).summarize_report(report)})


class KnowledgeView(APIView):
    """Situação da indexação dos manuais e reindexação manual."""

    permission_classes = [ACLPermission]
    acl_view = "media.view"
    acl_manage = "media.manage"

    def get(self, request):
        queryset = MediaAsset.objects.filter(category__in=INDEXABLE_CATEGORIES).select_related("ai_index", "equipment")
        if request.query_params.get("equipment"):
            queryset = queryset.filter(equipment_id=request.query_params["equipment"])
        items = []
        for media in queryset.order_by("equipment_id", "name"):
            index = getattr(media, "ai_index", None)
            if not media.file.name.lower().endswith(".pdf"):
                state, label = "UNSUPPORTED", "Formato não indexável (use PDF)"
            elif index is None:
                state, label = "PENDING", "Ainda não indexado"
            else:
                state, label = index.status, index.get_status_display()
            items.append({"media": media.pk, "name": media.name, "equipment": media.equipment_id, "state": state, "label": label,
                          "chunks": index.chunk_count if index else 0, "pages": index.page_count if index else 0})
        return Response({"results": items})

    def post(self, request):
        data = _valid(s.ReindexInputSerializer, request)
        queryset = MediaAsset.objects.filter(category__in=INDEXABLE_CATEGORIES)
        if data.get("media"):
            queryset = queryset.filter(pk=data["media"])
        if data.get("equipment"):
            queryset = queryset.filter(equipment=data["equipment"])
        results = [{"media": m.pk, "status": index_media(m).status} for m in queryset if is_indexable(m)]
        return Response({"indexed": len(results), "results": results})


def _valid(serializer_class, request, query=False):
    serializer = serializer_class(data=request.query_params if query else request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class RecommendationViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """Central de recomendações com aprovação humana e rastreabilidade."""
    from .models import AIRecommendation
    from .serializers import AIRecommendationSerializer
    queryset = AIRecommendation.objects.select_related("equipment", "generated_by", "decided_by", "closed_by", "service_order")
    serializer_class = AIRecommendationSerializer
    permission_classes = [ACLPermission]
    acl_view = "ai.assist"
    acl_manage = "ai.assist"

    def get_queryset(self):
        queryset = super().get_queryset()
        for key in ("kind", "status", "equipment"):
            value = self.request.query_params.get(key)
            if not value:
                continue
            if key == "status" and "," in value:  # ex.: status=ACCEPTED,PURCHASED
                queryset = queryset.filter(status__in=[v.strip() for v in value.split(",") if v.strip()])
            else:
                queryset = queryset.filter(**{key if key in ("kind", "status") else "equipment_id": value})
        return queryset

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        if not request.user.has_acl("maintenance.view") and not request.user.has_acl("assets.view"):
            raise PermissionDenied("Seu grupo não pode analisar equipamentos e manutenções.")
        from .recommendations import generate_preventive_recommendations, generate_purchase_recommendations
        from assets.models import Equipment
        kind = request.data.get("kind", "all")
        created = []
        if kind not in ("all", "preventive", "purchase"):
            return Response({"kind": "Use all, preventive ou purchase."}, status=http.HTTP_400_BAD_REQUEST)
        if kind in ("all", "preventive"):
            created.extend(generate_preventive_recommendations(request.user))
        if kind in ("all", "purchase"):
            equipment_id = request.data.get("equipment")
            if equipment_id:
                try:
                    Equipment.objects.get(pk=equipment_id)
                except (Equipment.DoesNotExist, ValueError, TypeError):
                    return Response({"equipment": "Equipamento não encontrado."}, status=http.HTTP_400_BAD_REQUEST)
            purchase_cost = request.data.get("purchase_cost")
            if purchase_cost not in (None, "") and not equipment_id:
                return Response({"purchase_cost": "Selecione um equipamento específico para associar o custo de aquisição."}, status=http.HTTP_400_BAD_REQUEST)
            if purchase_cost not in (None, ""):
                try:
                    from decimal import Decimal, InvalidOperation
                    purchase_cost = Decimal(str(purchase_cost))
                    if purchase_cost <= 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    return Response({"purchase_cost": "Informe um custo de aquisição positivo."}, status=http.HTTP_400_BAD_REQUEST)
            created.extend(generate_purchase_recommendations(request.user, equipment_id=equipment_id, purchase_cost=purchase_cost))
        if created:
            from core.models import AuditLog
            for item in created:
                AuditLog.objects.create(user=request.user, entity="AIRecommendation", record_id=str(item.pk),
                    action="RECOMMENDATION_GENERATED", data={"kind": item.kind, "equipment": item.equipment_id})
        return Response({"created": len(created), "results": self.get_serializer(created, many=True).data,
                         "message": "Análise concluída com base nos registros disponíveis."},
                        status=http.HTTP_201_CREATED if created else http.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        """Encerra uma sugestão de compra aceita: o gestor comprou o equipamento ou descartou a ideia."""
        from django.utils import timezone
        from .models import AIRecommendation
        recommendation = self.get_object()
        outcome = request.data.get("outcome")
        note = str(request.data.get("note", "")).strip()
        if outcome not in (AIRecommendation.Status.PURCHASED, AIRecommendation.Status.DISCARDED):
            return Response({"outcome": "Use PURCHASED ou DISCARDED."}, status=http.HTTP_400_BAD_REQUEST)
        if recommendation.kind != AIRecommendation.Kind.EQUIPMENT_PURCHASE:
            return Response({"detail": "Somente sugestões de aquisição podem ser encerradas."}, status=http.HTTP_400_BAD_REQUEST)
        if recommendation.status != AIRecommendation.Status.ACCEPTED:
            return Response({"detail": "Somente sugestões de compra aceitas (em avaliação) podem ser encerradas."}, status=http.HTTP_409_CONFLICT)
        recommendation.status = outcome
        recommendation.closed_by = request.user
        recommendation.closure_note = note
        recommendation.closed_at = timezone.now()
        recommendation.save(update_fields=("status", "closed_by", "closure_note", "closed_at"))
        from core.models import AuditLog
        AuditLog.objects.create(user=request.user, entity="AIRecommendation", record_id=str(recommendation.pk),
            action=f"RECOMMENDATION_{outcome}", data={"kind": recommendation.kind, "note": note})
        message = "Aquisição marcada como comprada e removida de \"Em avaliação\"." if outcome == AIRecommendation.Status.PURCHASED else "Sugestão descartada e removida de \"Em avaliação\"."
        return Response({"recommendation": self.get_serializer(recommendation).data, "message": message})

    @action(detail=True, methods=["post"], url_path="decision")
    def decision(self, request, pk=None):
        from django.db import transaction
        from django.utils import timezone
        from .models import AIRecommendation
        from maintenance.models import MaintenanceActivity, MaintenancePlan, ServiceOrder
        from rentals.services import refresh_equipment_status
        recommendation = self.get_object()
        decision = request.data.get("decision")
        reason = str(request.data.get("reason", "")).strip()
        if decision not in (AIRecommendation.Status.ACCEPTED, AIRecommendation.Status.REJECTED, AIRecommendation.Status.POSTPONED):
            return Response({"decision": "Use ACCEPTED, REJECTED ou POSTPONED."}, status=http.HTTP_400_BAD_REQUEST)
        if recommendation.status != AIRecommendation.Status.PENDING:
            return Response({"detail": "Esta recomendação já foi decidida."}, status=http.HTTP_409_CONFLICT)
        if decision == AIRecommendation.Status.ACCEPTED and recommendation.kind == AIRecommendation.Kind.PREVENTIVE_MAINTENANCE:
            if not request.user.has_acl("maintenance.manage"):
                raise PermissionDenied("Seu grupo não pode cadastrar planos de revisão periódica.")
            equipment = recommendation.equipment
            if equipment is None:
                return Response({"detail": "O equipamento da recomendação não está mais disponível."}, status=http.HTTP_409_CONFLICT)
            payload = recommendation.suggested_payload or {}
            plan_id = next(iter(payload.get("plan_ids", [])), None)
            existing_plan = MaintenancePlan.objects.filter(pk=plan_id, equipment=equipment).first() if plan_id else None
            # A recomendação é convertida em PLANO, não em uma ordem de serviço avulsa.
            # Se já há um plano vencido que originou a sugestão, ele é reativado/atualizado;
            # caso contrário, cria-se um plano periódico editável na área própria.
            with transaction.atomic():
                plan = existing_plan or MaintenancePlan(equipment=equipment)
                plan.name = plan.name or f"Revisão periódica recomendada — {equipment.name}"
                plan.maintenance_type = MaintenancePlan.Type.PREVENTIVE
                plan.criticality = ("HIGH" if payload.get("priority") == "HIGH" else "MEDIUM") if not existing_plan else plan.criticality
                first_review = None
                if not existing_plan:
                    # A recomendação nasce de falhas recentes ou de um plano vencido; por isso a primeira revisão
                    # é próxima (7 dias se prioridade alta, 30 se média) e só depois segue a periodicidade de 90 dias.
                    first_review = timezone.localdate() + timedelta(days=7 if payload.get("priority") == "HIGH" else 30)
                    plan.interval_days = 90
                    plan.next_due_date = first_review
                    plan.advance_notice_days = 15
                    plan.advance_notice_usage_hours = 10
                    plan.checklist = payload.get("checklist") or []
                plan.active = True
                plan.save()
                recommendation.status = decision
                recommendation.decided_by = request.user
                recommendation.decision_reason = reason
                recommendation.decided_at = timezone.now()
                recommendation.save(update_fields=("status", "decided_by", "decision_reason", "decided_at"))
                from core.models import AuditLog
                AuditLog.objects.create(user=request.user, entity="AIRecommendation", record_id=str(recommendation.pk),
                    action=f"RECOMMENDATION_{decision}", data={"kind": recommendation.kind, "maintenance_plan": plan.pk, "reason": reason})
            return Response({"recommendation": self.get_serializer(recommendation).data,
                             "maintenance_plan_id": plan.pk, "maintenance_plan_name": plan.name,
                             "message": "Plano de revisão periódica criado/atualizado." + (f" Primeira revisão prevista para {first_review:%d/%m/%Y}, depois a cada 90 dias." if first_review else "") + " Ajuste datas, periodicidade e checklist no plano. Nenhuma OS foi aberta agora."})
        recommendation.status = decision
        recommendation.decided_by = request.user
        recommendation.decision_reason = reason
        recommendation.decided_at = timezone.now()
        recommendation.save(update_fields=("status", "decided_by", "decision_reason", "decided_at"))
        from core.models import AuditLog
        AuditLog.objects.create(user=request.user, entity="AIRecommendation", record_id=str(recommendation.pk),
            action=f"RECOMMENDATION_{decision}", data={"kind": recommendation.kind, "reason": reason})
        message = "Sugestão aceita e guardada em Assistente de IA › Sugestões de compra; nenhuma compra foi realizada." if recommendation.kind == AIRecommendation.Kind.EQUIPMENT_PURCHASE and decision == AIRecommendation.Status.ACCEPTED else "Decisão registrada."
        return Response({"recommendation": self.get_serializer(recommendation).data, "message": message})


class UnfulfilledDemandViewSet(ListModelMixin, CreateModelMixin, GenericViewSet):
    from .models import UnfulfilledDemand
    from .serializers import UnfulfilledDemandSerializer
    queryset = UnfulfilledDemand.objects.select_related("equipment", "category", "customer", "recorded_by")
    serializer_class = UnfulfilledDemandSerializer
    permission_classes = [ACLPermission]
    acl_view = ("ai.assist", "dashboard.view", "rentals.view")
    # Quem monta orçamentos (vendedor) também precisa registrar o pedido que não pôde ser atendido.
    acl_manage = ("ai.assist", "rentals.manage")

    def get_queryset(self):
        queryset = super().get_queryset()
        for key, field in (("equipment", "equipment_id"), ("category", "category_id"), ("customer", "customer_id")):
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    def perform_create(self, serializer):
        demand = serializer.save()
        from core.models import AuditLog
        AuditLog.objects.create(user=self.request.user, entity="UnfulfilledDemand", record_id=str(demand.pk),
            action="UNFULFILLED_DEMAND_RECORDED", data={"equipment": demand.equipment_id, "category": demand.category_id,
            "requested_item": demand.requested_item, "customer": demand.customer_id, "quantity": demand.quantity,
            "requested_days": demand.requested_days, "requested_at": str(demand.requested_at), "reason": demand.reason})
