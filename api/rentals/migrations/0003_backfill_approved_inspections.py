from django.db import migrations


DEFAULT_CHECKLIST = (
    "Estrutura e carenagens sem avarias",
    "Proteções e dispositivos de segurança",
    "Níveis, cabos, mangueiras e conexões",
    "Teste de funcionamento e parada de emergência",
    "Limpeza e acessórios conferidos",
)


def backfill_approved_rentals(apps, schema_editor):
    RentalQuote = apps.get_model("rentals", "RentalQuote")
    RentalInspection = apps.get_model("rentals", "RentalInspection")
    for quote in RentalQuote.objects.filter(status="APPROVED").iterator():
        changed = []
        if not quote.reserved_by_id:
            quote.reserved_by_id = quote.created_by_id
            changed.append("reserved_by")
        if not quote.reserved_at:
            quote.reserved_at = quote.updated_at
            changed.append("reserved_at")
        if changed:
            quote.save(update_fields=changed)
        for item in quote.items.select_related("equipment__category"):
            configured = item.equipment.category.pre_rental_checklist or DEFAULT_CHECKLIST
            checklist = [
                {"id": str(index + 1), "label": entry.get("label", "") if isinstance(entry, dict) else str(entry), "status": "PENDING", "notes": ""}
                for index, entry in enumerate(configured)
            ]
            RentalInspection.objects.get_or_create(
                quote_id=quote.pk,
                equipment_id=item.equipment_id,
                inspection_type="PRE_RENTAL",
                defaults={"checklist": checklist},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0004_mediaasset_rental_inspection"),
        ("rentals", "0002_rentalquote_cancellation_reason_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_approved_rentals, migrations.RunPython.noop),
    ]
