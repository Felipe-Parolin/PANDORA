from rest_framework import serializers
from .models import PurchaseRecommendation, MarketingCampaign

class PurchaseRecommendationSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True)
    class Meta:
        model = PurchaseRecommendation
        fields = "__all__"
        read_only_fields = ("current_total", "current_available", "demand_events", "maintenance_orders", "unavailable_days", "evidence", "rationale", "created_at", "updated_at", "decided_by", "decided_at")

class MarketingCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketingCampaign
        fields = "__all__"
        read_only_fields = ("status", "sent_at", "recipient_count", "result_log", "created_by", "created_at")
