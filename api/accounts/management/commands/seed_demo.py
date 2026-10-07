from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.acl import DEFAULT_GROUPS
from accounts.models import AccessGroup, User
from assets.models import Equipment, EquipmentCategory
from customers.models import Customer
from maintenance.models import MaintenancePlan, ServiceOrder
from rentals.models import RentalItem, RentalQuote


class Command(BaseCommand):
    help = "Cria uma base demonstrativa idempotente para o PANDORA."

    def handle(self, *args, **options):
        users = [
            ("admin@pandora.local", "Administrador PANDORA", User.Role.ADMIN),
            ("vendas@pandora.local", "Marina Vendas", User.Role.SALES),
            ("manutencao@pandora.local", "Carlos Manutenção", User.Role.MAINTENANCE),
        ]
        created_users = {}
        for email, name, role in users:
            group, _ = AccessGroup.objects.get_or_create(
                name=DEFAULT_GROUPS[role]["name"],
                defaults={
                    "description": DEFAULT_GROUPS[role]["description"],
                    "permissions": DEFAULT_GROUPS[role]["permissions"],
                    "is_system": True,
                },
            )
            if group.is_system:
                group.description = DEFAULT_GROUPS[role]["description"]
                group.permissions = DEFAULT_GROUPS[role]["permissions"]
                group.save(update_fields=("description", "permissions", "updated_at"))
            user, _ = User.objects.get_or_create(email=email, defaults={"full_name": name, "role": role, "is_staff": role == User.Role.ADMIN})
            user.full_name, user.role, user.is_active = name, role, True
            user.access_group = group
            user.set_password("Pandora@123")
            user.save()
            created_users[role] = user

        customers = [
            ("Construtora Horizonte Ltda", "12345678000190", "PJ", "compras@horizonte.com.br", "19999990001"),
            ("Rafael de Lima", "12345678909", "PF", "rafael@example.com", "19999990002"),
            ("Obra Certa Engenharia", "98765432000110", "PJ", "locacoes@obracerta.com.br", "19999990003"),
        ]
        customer_objects = []
        for name, document, kind, email, phone in customers:
            customer, _ = Customer.objects.update_or_create(document=document, defaults={"name": name, "person_type": kind, "email": email, "phone": phone, "is_active": True})
            customer_objects.append(customer)

        compaction, _ = EquipmentCategory.objects.get_or_create(name="Compactação", defaults={"description": "Compactadores e placas vibratórias", "default_daily_rate": 190})
        cutting, _ = EquipmentCategory.objects.get_or_create(name="Corte", defaults={"description": "Cortadoras e serras", "default_daily_rate": 145})
        lifting, _ = EquipmentCategory.objects.get_or_create(name="Elevação", defaults={"description": "Andaimes e elevadores", "default_daily_rate": 260})
        equipment_data = [
            ("EQ-001", "Compactador de Solo", "Wacker", "WP1550", "WK-1550-2026-01", compaction, 190),
            ("EQ-002", "Cortadora de Piso", "Husqvarna", "FS400", "HQ-FS400-045", cutting, 145),
            ("EQ-003", "Betoneira 400L", "Menegotti", "Prime 400", "MN-400-118", compaction, 120),
            ("EQ-004", "Elevador de Obra", "C3", "EO-500", "C3-EO500-77", lifting, 260),
        ]
        equipment_objects = []
        for code, name, brand, model, serial, category, rate in equipment_data:
            equipment, _ = Equipment.objects.update_or_create(internal_code=code, defaults={"name": name, "brand": brand, "model": model, "serial_number": serial, "category": category, "daily_rate": rate, "status": Equipment.Status.AVAILABLE})
            equipment_objects.append(equipment)

        MaintenancePlan.objects.get_or_create(
            equipment=equipment_objects[0], name="Revisão preventiva trimestral",
            defaults={"maintenance_type": MaintenancePlan.Type.PREVENTIVE, "interval_days": 90, "next_due_date": timezone.localdate() + timedelta(days=8), "criticality": MaintenancePlan.Criticality.HIGH, "checklist": ["Nível de óleo", "Filtro", "Teste funcional"]},
        )
        ServiceOrder.objects.get_or_create(
            number="OS-DEMO-001",
            defaults={"equipment": equipment_objects[2], "maintenance_type": ServiceOrder.Type.SCHEDULED, "status": ServiceOrder.Status.SCHEDULED, "symptoms": "Revisão antes da próxima locação.", "opened_by": created_users[User.Role.MAINTENANCE], "technician": created_users[User.Role.MAINTENANCE], "scheduled_at": timezone.now() + timedelta(days=2)},
        )
        ServiceOrder.objects.get_or_create(
            number="OS-DEMO-002",
            defaults={"equipment": equipment_objects[2], "maintenance_type": ServiceOrder.Type.CORRECTIVE, "status": ServiceOrder.Status.OPEN, "priority": "ALTA", "symptoms": "Motor perde força após alguns minutos de uso.", "opened_by": created_users[User.Role.ADMIN]},
        )
        ServiceOrder.objects.get_or_create(
            number="OS-DEMO-003",
            defaults={"equipment": equipment_objects[3], "maintenance_type": ServiceOrder.Type.PREVENTIVE, "status": ServiceOrder.Status.IN_PROGRESS, "symptoms": "Inspeção do sistema de elevação e cabos.", "diagnosis": "Desgaste no cabo principal em avaliação.", "opened_by": created_users[User.Role.MAINTENANCE], "technician": created_users[User.Role.MAINTENANCE]},
        )
        ServiceOrder.objects.get_or_create(
            number="OS-DEMO-004",
            defaults={"equipment": equipment_objects[0], "maintenance_type": ServiceOrder.Type.CORRECTIVE, "status": ServiceOrder.Status.ABANDONED, "symptoms": "Vibração excessiva durante a compactação.", "diagnosis": "Coxim precisa ser substituído.", "abandoned_reason": "Peça incompatível recebida; atendimento deve ser redistribuído após nova compra.", "opened_by": created_users[User.Role.MAINTENANCE], "technician": created_users[User.Role.MAINTENANCE]},
        )
        ServiceOrder.objects.get_or_create(
            number="OS-DEMO-005",
            defaults={"equipment": equipment_objects[1], "maintenance_type": ServiceOrder.Type.POST_RENTAL, "status": ServiceOrder.Status.COMPLETED, "symptoms": "Inspeção de retorno.", "diagnosis": "Equipamento sem avarias.", "final_tests": "Partida, corte e parada de emergência aprovados.", "released": True, "opened_by": created_users[User.Role.MAINTENANCE], "technician": created_users[User.Role.MAINTENANCE]},
        )
        quote, created = RentalQuote.objects.get_or_create(
            number="ORC-DEMO-001",
            defaults={"customer": customer_objects[0], "start_date": timezone.localdate() + timedelta(days=3), "end_date": timezone.localdate() + timedelta(days=7), "status": RentalQuote.Status.SENT, "conditions": "Retirada e devolução no balcão. Combustível por conta do cliente.", "created_by": created_users[User.Role.SALES]},
        )
        if created:
            RentalItem.objects.create(quote=quote, equipment=equipment_objects[0], daily_rate=Decimal("190"), quantity_days=5, total=Decimal("950"))
            quote.recalculate()

        self.stdout.write(self.style.SUCCESS("Base demonstrativa criada. Login: admin@pandora.local / Pandora@123"))
