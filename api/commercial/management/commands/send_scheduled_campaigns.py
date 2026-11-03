from django.conf import settings
from django.db import transaction
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.html import strip_tags

from customers.models import Customer
from commercial.models import MarketingCampaign
from commercial.views import render_campaign_html


class Command(BaseCommand):
    help = "Envia campanhas de marketing preparadas cuja data de envio já chegou."

    def handle(self, *args, **options):
        if not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL:
            self.stderr.write("SMTP não configurado; nenhuma campanha foi enviada.")
            return
        now = timezone.now()
        campaign_ids = list(MarketingCampaign.objects.filter(
            status=MarketingCampaign.Status.READY,
            scheduled_at__isnull=False,
            scheduled_at__lte=now,
        ).order_by("scheduled_at").values_list("pk", flat=True))
        sent_campaigns = 0
        for campaign_id in campaign_ids:
            with transaction.atomic():
                campaign = MarketingCampaign.objects.select_for_update().get(pk=campaign_id)
                if campaign.status != MarketingCampaign.Status.READY or not campaign.scheduled_at or campaign.scheduled_at > timezone.now():
                    continue
                prepared = campaign.result_log[0].get("prepared_customer_ids", []) if campaign.result_log else []
                recipients = Customer.objects.filter(
                    pk__in=prepared, is_active=True, marketing_opt_in=True
                ).exclude(email="")
                logs, sent = [], 0
                for customer in recipients.iterator():
                    base = getattr(settings, "BACKEND_PUBLIC_URL", "").rstrip("/")
                    unsubscribe = f"{base}/api/marketing/unsubscribe/{customer.marketing_unsubscribe_token}/"
                    html = render_campaign_html(campaign, unsubscribe)
                    message = EmailMultiAlternatives(
                        campaign.subject, strip_tags(html), settings.DEFAULT_FROM_EMAIL, [customer.email]
                    )
                    message.attach_alternative(html, "text/html")
                    try:
                        message.send(fail_silently=False)
                        sent += 1
                        logs.append({"customer_id": customer.pk, "email": customer.email, "sent": True})
                    except Exception as exc:  # delivery failures are retained for audit
                        logs.append({"customer_id": customer.pk, "email": customer.email, "sent": False, "error": str(exc)[:300]})
                campaign.recipient_count = len(logs)
                campaign.result_log = logs
                campaign.status = (MarketingCampaign.Status.SENT if sent == len(logs) and sent else
                                   MarketingCampaign.Status.PARTIAL if sent else MarketingCampaign.Status.FAILED)
                campaign.sent_at = now if sent else None
                campaign.save(update_fields=("recipient_count", "result_log", "status", "sent_at"))
                sent_campaigns += 1
        self.stdout.write(self.style.SUCCESS(f"Campanhas processadas: {sent_campaigns}"))
