import uuid

from django.db import migrations
from django.utils import timezone


def backfill_return_orders(apps, schema_editor):
    RentalInspection = apps.get_model("rentals", "RentalInspection")
    ServiceOrder = apps.get_model("maintenance", "ServiceOrder")
    inspections = RentalInspection.objects.filter(
        inspection_type="RETURN", quote__status__in=("RETURNED", "COMPLETED")
    ).select_related("quote")
    for inspection in inspections.iterator():
        needs_repair = inspection.result == "BLOCKED" or inspection.condition in ("DAMAGED", "CRITICAL")
        completed = inspection.result in ("APPROVED", "APPROVED_WITH_NOTES") and not needs_repair
        actor_id = inspection.performed_by_id or inspection.quote.returned_by_id or inspection.quote.created_by_id
        ServiceOrder.objects.get_or_create(
            rental_inspection_id=inspection.pk,
            defaults={
                "number": f"OS-{timezone.localdate().year}-{uuid.uuid4().hex[:8].upper()}",
                "equipment_id": inspection.equipment_id,
                "maintenance_type": "POST_RENTAL",
                "status": "COMPLETED" if completed else "IN_PROGRESS" if needs_repair else "OPEN",
                "priority": "CRÍTICA" if inspection.critical_impediment else "ALTA" if needs_repair else "NORMAL",
                "symptoms": f"Inspeção final após devolução da locação {inspection.quote.number}.",
                "diagnosis": inspection.observations if needs_repair else "",
                "opened_by_id": inspection.quote.returned_by_id or inspection.quote.created_by_id,
                "technician_id": actor_id if completed or needs_repair else None,
                "final_tests": "Checklist de devolução concluído." if completed else "",
                "released": completed,
                "closed_at": (inspection.performed_at or inspection.quote.returned_at) if completed else None,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0004_serviceorder_plan_due_date_and_more"),
        ("rentals", "0007_quote_address_complements"),
    ]

    operations = [migrations.RunPython(backfill_return_orders, migrations.RunPython.noop)]
