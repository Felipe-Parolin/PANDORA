import uuid

from django.db import migrations


def create_pre_rental_orders(apps, schema_editor):
    RentalInspection = apps.get_model("rentals", "RentalInspection")
    ServiceOrder = apps.get_model("maintenance", "ServiceOrder")
    inspections = RentalInspection.objects.filter(inspection_type="PRE_RENTAL", quote__status="APPROVED").select_related("quote")
    for inspection in inspections.iterator():
        result = inspection.result
        completed = result in {"APPROVED", "APPROVED_WITH_NOTES"}
        blocked = result == "BLOCKED"
        ServiceOrder.objects.get_or_create(
            rental_inspection_id=inspection.pk,
            defaults={
                "number": f"OS-OS-{uuid.uuid4().hex[:8].upper()}",
                "equipment_id": inspection.equipment_id,
                "maintenance_type": "PRE_RENTAL",
                "status": "COMPLETED" if completed else "IN_PROGRESS" if blocked else "OPEN",
                "priority": "CRÍTICA" if blocked else "ALTA",
                "symptoms": f"Inspeção pré-locação obrigatória para a reserva {inspection.quote.number}.",
                "diagnosis": inspection.observations if blocked else "",
                "opened_by_id": inspection.quote.reserved_by_id or inspection.quote.created_by_id,
                "technician_id": (inspection.performed_by_id or inspection.quote.created_by_id) if completed or blocked else None,
                "final_tests": "Checklist pré-locação concluído." if completed else "",
                "released": completed,
                "closed_at": inspection.performed_at if completed else None,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0003_maintenanceplan_advance_notice_days_and_more"),
        ("rentals", "0003_backfill_approved_inspections"),
    ]

    operations = [migrations.RunPython(create_pre_rental_orders, migrations.RunPython.noop)]
