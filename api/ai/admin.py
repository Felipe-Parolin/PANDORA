from django.contrib import admin

from .models import AIConsultation, AIDecision, AIRecommendation, ManualChunk, ManualIndex, UnfulfilledDemand

admin.site.register(AIConsultation)
admin.site.register(AIDecision)
admin.site.register(ManualIndex)
admin.site.register(ManualChunk)

admin.site.register(AIRecommendation)
admin.site.register(UnfulfilledDemand)
