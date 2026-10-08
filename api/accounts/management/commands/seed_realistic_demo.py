"""Reproducible, fictional rental-operation dataset for local demonstrations."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.acl import DEFAULT_GROUPS
from accounts.models import AccessGroup, User
from assets.models import Equipment, EquipmentCategory, MediaAsset
from customers.models import Customer
from logistics.models import TransportTask, Vehicle
from maintenance.models import MaintenancePlan, ServiceOrder
from maintenance.services import generate_due_preventive_orders
from rentals.models import RentalInspection, RentalItem, RentalQuote
from rentals.services import ensure_inspections, ensure_pre_rental_orders, ensure_return_orders, refresh_equipment_status


def sample_cpf(base):
    digits = [int(value) for value in base]
    for position in (9, 10):
        remainder = sum(digits[index] * (position + 1 - index) for index in range(position)) % 11
        digits.append(0 if remainder < 2 else 11 - remainder)
    return "".join(map(str, digits))


def sample_cnpj(base):
    digits = [int(value) for value in base]
    for weights in ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2), (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)):
        remainder = sum(value * weight for value, weight in zip(digits, weights)) % 11
        digits.append(0 if remainder < 2 else 11 - remainder)
    return "".join(map(str, digits))


class Command(BaseCommand):
    help = "Popula apenas o PostgreSQL local com uma operação fictícia, fotografias e fluxos consistentes."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="Pandora@123", help="Senha temporária dos usuários demonstrativos")

    @transaction.atomic
    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if not settings.DEBUG or database["ENGINE"] != "django.db.backends.postgresql" or database["HOST"] not in ("localhost", "127.0.0.1") or database["NAME"] != "pandora_db":
            raise CommandError("Este comando só pode ser usado na base PostgreSQL local pandora_db em modo de desenvolvimento.")
        today = timezone.localdate()
        password = options["password"]

        groups = {}
        for role, definition in DEFAULT_GROUPS.items():
            groups[role], _ = AccessGroup.objects.update_or_create(
                name=definition["name"],
                defaults={"description": definition["description"], "permissions": definition["permissions"], "is_system": True},
            )
        logistics_group, _ = AccessGroup.objects.update_or_create(
            name="Logística",
            defaults={"description": "Planejamento de viagens, veículos e consulta de locações.", "permissions": ["dashboard.view", "logistics.view", "logistics.manage", "rentals.view", "assets.view"], "is_system": False},
        )
        people = {}
        for key, email, name, role, group in (
            ("admin", "admin@pandora.local", "Administrador PANDORA", User.Role.ADMIN, groups["ADMIN"]),
            ("sales", "vendas@pandora.local", "Marina Costa · Vendas", User.Role.SALES, groups["SALES"]),
            ("tech", "manutencao@pandora.local", "Carlos Almeida · Manutenção", User.Role.MAINTENANCE, groups["MAINTENANCE"]),
            ("driver", "logistica@pandora.local", "Juliana Ribeiro · Logística", User.Role.SALES, logistics_group),
        ):
            user, _ = User.objects.get_or_create(email=email, defaults={"full_name": name})
            user.full_name, user.role, user.access_group = name, role, group
            user.is_active = True
            user.is_staff = key == "admin"
            user.is_superuser = key == "admin"
            user.set_password(password)
            user.save()
            people[key] = user

        customer_data = (
            ("obra", "Construtora Vila Nova Ltda", "PJ", sample_cnpj("112223330001"), "compras@vilanova.example.invalid", "(19) 99921-1101", "Rua Dr. Armando Salles de Oliveira, 328, Centro, Leme/SP", "Obra residencial; entrega pela manhã."),
            ("engenharia", "Forte Engenharia e Reformas Ltda", "PJ", sample_cnpj("223334440001"), "obras@forte.example.invalid", "(19) 99921-1102", "Av. 29 de Agosto, 840, Cidade Jardim, Leme/SP", "Contato de obra: encarregado Paulo."),
            ("reforma", "Ana Paula Martins", "PF", sample_cpf("246813579"), "ana.martins@example.invalid", "(19) 99921-1103", "Rua das Palmeiras, 144, Santa Rita, Leme/SP", "Reforma residencial; retirar no balcão."),
            ("condominio", "Condomínio Jardim das Flores", "PJ", sample_cnpj("334445550001"), "sindico@jardim.example.invalid", "(19) 99921-1104", "Rua Rafael de Barros, 1010, Centro, Leme/SP", "Solicitar identificação do motorista na portaria."),
            ("pedreiro", "Roberto Silva", "PF", sample_cpf("357924681"), "roberto.silva@example.invalid", "(19) 99921-1105", "Rua do Bosque, 72, Bela Vista, Leme/SP", "Cliente recorrente de pequenas reformas."),
        )
        customers = {}
        for key, name, kind, document, email, phone, address, notes in customer_data:
            customers[key], _ = Customer.objects.update_or_create(
                document=document, defaults={"person_type": kind, "name": name, "email": email, "phone": phone, "address": address, "notes": notes, "is_active": True},
            )

        categories = {}
        for key, name, rate, checklist in (
            ("compactacao", "Compactação", "190", ["Base e coxins", "Nível do óleo", "Partida e vibração", "Proteções e parada"]),
            ("concreto", "Preparo de concreto", "130", ["Tambor e cremalheira", "Cabo elétrico", "Partida e rotação", "Limpeza"]),
            ("corte", "Corte de piso", "220", ["Disco e proteção", "Água de refrigeração", "Partida e parada", "Rodas e guidão"]),
            ("demolicao", "Demolição", "150", ["Ponteira e encaixe", "Cabo elétrico", "Teste de impacto", "Maleta e acessórios"]),
            ("energia", "Energia temporária", "290", ["Óleo e combustível", "Tomadas e disjuntores", "Partida e tensão", "Aterramento"]),
            ("acesso", "Acesso e andaimes", "120", ["Travessas e soldas", "Rodízios e travas", "Plataforma", "Guarda-corpo"]),
        ):
            categories[key], _ = EquipmentCategory.objects.update_or_create(
                name=name, defaults={"description": f"Equipamentos para {name.lower()} em canteiros de obra.", "default_daily_rate": Decimal(rate), "pre_rental_checklist": checklist, "return_checklist": checklist},
            )
        equipment_data = (
            ("EQ-001", "Compactador de solo reversível", "Bomag", "BPR 25/50", "DEMO-BPR-2026-001", "compactacao", "190", "compactador.png", 430),
            ("EQ-002", "Cortadora de piso 450 mm", "Husqvarna", "FS 400 LV", "DEMO-FS400-2026-002", "corte", "220", "cortadora.png", 286),
            ("EQ-003", "Betoneira elétrica 400 L", "Menegotti", "Prime 400", "DEMO-PR400-2026-003", "concreto", "130", "betoneira.png", 612),
            ("EQ-004", "Martelete rompedor 30 kg", "Bosch", "GSH 27 VC", "DEMO-GSH27-2026-004", "demolicao", "150", "martelete.png", 375),
            ("EQ-005", "Gerador diesel 10 kVA", "Toyama", "TDG 10000", "DEMO-TDG10-2026-005", "energia", "290", "gerador.png", 984),
            ("EQ-006", "Andaime tubular com rodízios", "Mills", "Torre 2 m", "DEMO-AND-2026-006", "acesso", "120", "andaime.png", 180),
        )
        equipment = {}
        asset_folder = settings.BASE_DIR / "seed_assets" / "equipment"
        for code, name, brand, model, serial, category_key, rate, image, hours in equipment_data:
            equipment[code], _ = Equipment.objects.update_or_create(
                internal_code=code, defaults={"name": name, "brand": brand, "model": model, "serial_number": serial, "category": categories[category_key], "daily_rate": Decimal(rate), "current_usage_hours": hours, "technical_details": "Equipamento de demonstração. Conferir checklist e acessórios na entrega."},
            )
            if not MediaAsset.objects.filter(equipment=equipment[code], category=MediaAsset.Category.PHOTO).exists():
                photo = MediaAsset(name=f"Foto de catálogo · {name}", category=MediaAsset.Category.PHOTO, description="Imagem ilustrativa gerada para a base de demonstração.", equipment=equipment[code], uploaded_by=people["admin"])
                with (asset_folder / image).open("rb") as source:
                    photo.file.save(f"{code.lower()}-{image}", File(source), save=True)

        vehicles = {}
        for key, plate, brand, model, kind, capacity, notes in (
            ("pickup", "PDR1A23", "Fiat", "Strada Endurance", Vehicle.Type.PICKUP, 720, "Entregas leves e ferramentas."),
            ("truck", "PDR2B34", "Mercedes-Benz", "Accelo 815", Vehicle.Type.TRUCK, 4200, "Equipamentos pesados; exige agendamento de descarga."),
            ("van", "PDR3C45", "Renault", "Master Furgão", Vehicle.Type.VAN, 1500, "Retiradas e entregas urbanas."),
        ):
            vehicles[key], _ = Vehicle.objects.update_or_create(plate=plate, defaults={"brand": brand, "model": model, "vehicle_type": kind, "capacity_kg": capacity, "notes": notes, "status": Vehicle.Status.AVAILABLE})

        scenarios = (
            ("ORC-CEN-001", "obra", "EQ-001", 2, 5, RentalQuote.Status.APPROVED, True, "80", "0"),
            ("ORC-CEN-002", "engenharia", "EQ-002", -2, 3, RentalQuote.Status.ACTIVE, True, "95", "5"),
            ("ORC-CEN-003", "condominio", "EQ-003", -7, -3, RentalQuote.Status.RETURNED, False, "0", "0"),
            ("ORC-CEN-004", "reforma", "EQ-004", -16, -12, RentalQuote.Status.COMPLETED, False, "0", "0"),
            ("ORC-CEN-005", "pedreiro", "EQ-005", 12, 14, RentalQuote.Status.DRAFT, False, "0", "0"),
            ("ORC-CEN-006", "obra", "EQ-006", 8, 11, RentalQuote.Status.SENT, False, "0", "3"),
        )
        for number, customer_key, equipment_code, start, end, target, delivery, fee, discount in scenarios:
            customer = customers[customer_key]
            quote, created = RentalQuote.objects.get_or_create(
                number=number,
                defaults={"customer": customer, "start_date": today + timedelta(days=start), "end_date": today + timedelta(days=end), "created_by": people["sales"], "conditions": "Locação somente do equipamento. Entrega, combustível e devolução conforme orçamento.", "delivery_transport_required": delivery, "delivery_address": customer.address if delivery else "", "delivery_complement": "Portaria da obra" if delivery else "", "transport_fee": Decimal(fee), "discount_percent": Decimal(discount)},
            )
            if created:
                RentalItem.objects.create(quote=quote, equipment=equipment[equipment_code], daily_rate=equipment[equipment_code].daily_rate, quantity_days=end - start + 1)
                quote.recalculate()
            if target == RentalQuote.Status.DRAFT:
                continue
            if target == RentalQuote.Status.SENT:
                quote.status = target
                quote.save(update_fields=("status", "updated_at"))
                continue
            if quote.status == RentalQuote.Status.DRAFT:
                quote.status, quote.reserved_by, quote.reserved_at = RentalQuote.Status.APPROVED, people["sales"], timezone.now()
                quote.save(update_fields=("status", "reserved_by", "reserved_at", "updated_at"))
            ensure_inspections(quote, RentalInspection.Type.PRE_RENTAL)
            ensure_pre_rental_orders(quote, people["sales"])
            pre = quote.inspections.get(inspection_type=RentalInspection.Type.PRE_RENTAL, equipment=equipment[equipment_code])
            pre_order = pre.service_order
            if target == RentalQuote.Status.APPROVED:
                task, _ = TransportTask.objects.get_or_create(quote=quote, leg=TransportTask.Leg.DELIVERY, defaults={"address": quote.delivery_address, "complement": quote.delivery_complement, "scheduled_at": timezone.make_aware(datetime.combine(today + timedelta(days=2), time(8))), "vehicle": vehicles["truck"], "driver": people["driver"], "created_by": people["sales"]})
                continue
            if pre.result == RentalInspection.Result.PENDING:
                pre.result, pre.condition = RentalInspection.Result.APPROVED, RentalInspection.Condition.GOOD
                pre.checklist = [{**row, "status": "OK"} for row in pre.checklist]
                pre.performed_by, pre.performed_at = people["tech"], timezone.now()
                pre.save()
                pre_order.status, pre_order.technician = ServiceOrder.Status.COMPLETED, people["tech"]
                pre_order.final_tests, pre_order.released = "Checklist e teste funcional aprovados.", True
                pre_order.save()
            if delivery:
                TransportTask.objects.get_or_create(quote=quote, leg=TransportTask.Leg.DELIVERY, defaults={"address": quote.delivery_address, "complement": quote.delivery_complement, "scheduled_at": timezone.now() - timedelta(days=2), "departed_at": timezone.now() - timedelta(days=2), "completed_at": timezone.now() - timedelta(days=2), "status": TransportTask.Status.COMPLETED, "vehicle": vehicles["van"], "driver": people["driver"], "created_by": people["sales"]})
            if quote.status == RentalQuote.Status.APPROVED:
                quote.status, quote.delivered_by, quote.delivered_at = RentalQuote.Status.ACTIVE, people["sales"], timezone.now() - timedelta(days=max(1, -start))
                quote.delivery_conditions = "Acessórios conferidos e equipamento entregue funcionando."
                quote.save(update_fields=("status", "delivered_by", "delivered_at", "delivery_conditions", "updated_at"))
            if target == RentalQuote.Status.ACTIVE:
                continue
            ensure_inspections(quote, RentalInspection.Type.RETURN)
            if quote.status == RentalQuote.Status.ACTIVE:
                quote.status, quote.returned_by, quote.returned_at = RentalQuote.Status.RETURNED, people["sales"], timezone.now() + timedelta(days=end)
                quote.return_conditions = "Recebido no balcão; aguardando inspeção final."
                quote.save(update_fields=("status", "returned_by", "returned_at", "return_conditions", "updated_at"))
            return_inspection = quote.inspections.get(inspection_type=RentalInspection.Type.RETURN, equipment=equipment[equipment_code])
            if target == RentalQuote.Status.COMPLETED and return_inspection.result == RentalInspection.Result.PENDING:
                return_inspection.result, return_inspection.condition = RentalInspection.Result.APPROVED, RentalInspection.Condition.GOOD
                return_inspection.checklist = [{**row, "status": "OK"} for row in return_inspection.checklist]
                return_inspection.performed_by, return_inspection.performed_at = people["tech"], timezone.now()
                return_inspection.observations = "Sem avarias ou acessórios faltantes."
                return_inspection.save()
            ensure_return_orders(quote, people["sales"])
            if target == RentalQuote.Status.COMPLETED and quote.status == RentalQuote.Status.RETURNED:
                quote.status = RentalQuote.Status.COMPLETED
                quote.save(update_fields=("status", "updated_at"))

        ServiceOrder.objects.get_or_create(
            number="OS-CEN-CORRETIVA",
            defaults={"equipment": equipment["EQ-005"], "maintenance_type": ServiceOrder.Type.CORRECTIVE, "status": ServiceOrder.Status.WAITING_PARTS, "priority": "ALTA", "symptoms": "Gerador oscila a tensão após aquecer.", "diagnosis": "Regulador de tensão fora da faixa; peça solicitada.", "parts_used": "Regulador de tensão aguardando entrega", "opened_by": people["tech"], "technician": people["tech"]},
        )
        MaintenancePlan.objects.get_or_create(
            equipment=equipment["EQ-004"], name="Revisão a cada 90 dias",
            defaults={"maintenance_type": MaintenancePlan.Type.PREVENTIVE, "interval_days": 90, "next_due_date": today, "last_service_date": today - timedelta(days=90), "criticality": MaintenancePlan.Criticality.HIGH, "checklist": ["Escovas do motor", "Lubrificação", "Teste de impacto", "Isolamento do cabo"]},
        )
        MaintenancePlan.objects.get_or_create(
            equipment=equipment["EQ-006"], name="Inspeção estrutural a cada 60 dias",
            defaults={"maintenance_type": MaintenancePlan.Type.PREVENTIVE, "interval_days": 60, "next_due_date": today + timedelta(days=18), "criticality": MaintenancePlan.Criticality.HIGH, "checklist": ["Soldas", "Travamentos", "Plataforma", "Rodízios"]},
        )
        generate_due_preventive_orders(today=today)
        for item in equipment.values():
            refresh_equipment_status(item)

        self.stdout.write(self.style.SUCCESS(
            f"Base fictícia pronta: {Customer.objects.count()} clientes, {Equipment.objects.count()} equipamentos, "
            f"{MediaAsset.objects.count()} fotos, {Vehicle.objects.count()} veículos, {RentalQuote.objects.count()} orçamentos, "
            f"{ServiceOrder.objects.count()} OS. Login local: admin@pandora.local / {password}"
        ))
