from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("consultations", views.ConsultationViewSet, basename="ai-consultation")
router.register("recommendations", views.RecommendationViewSet, basename="ai-recommendation")
router.register("unfulfilled-demands", views.UnfulfilledDemandViewSet, basename="ai-unfulfilled-demand")

urlpatterns = [
    path("status/", views.StatusView.as_view(), name="ai-status"),
    path("search/", views.SearchView.as_view(), name="ai-search"),
    path("diagnose/", views.DiagnoseView.as_view(), name="ai-diagnose"),
    path("ask/", views.AskView.as_view(), name="ai-ask"),
    path("transcribe/", views.TranscribeView.as_view(), name="ai-transcribe"),
    path("extract-report/", views.ExtractReportView.as_view(), name="ai-extract-report"),
    path("recurrence/", views.RecurrenceView.as_view(), name="ai-recurrence"),
    path("recurrence/<int:equipment_id>/", views.RecurrenceView.as_view(), name="ai-recurrence-detail"),
    path("reports/operational/", views.OperationalReportView.as_view(), name="ai-report"),
    path("reports/summary/", views.ReportSummaryView.as_view(), name="ai-report-summary"),
    path("knowledge/", views.KnowledgeView.as_view(), name="ai-knowledge"),
    path("", include(router.urls)),
]
