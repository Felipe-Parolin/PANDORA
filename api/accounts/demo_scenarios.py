"""Cenários fictícios, locais e reproduzíveis. Não consulta IA, mapas ou SMTP."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.core.files import File
from django.core.management import call_command
from django.utils import timezone

from ai.models import AIConsultation, AIDecision, UnfulfilledDemand
from assets.models import Equipment, EquipmentCategory, MediaAsset
from commercial.models import MarketingCampaign, Payment, PurchaseRecommendation, Receivable
from commercial.receivables import payment_preview, post_quote_receivable, settle
from customers.models import Customer
from logistics.models import Vehicle
from logistics.services import ensure_transport_task, task_items
from maintenance.models import MaintenanceActivity, MaintenancePlan, ServiceOrder
from maintenance.services import generate_due_preventive_orders
from rentals.documents import snapshot_for, snapshot_hash
from rentals.models import RentalDocument, RentalInspection, RentalItem, RentalQuote
from rentals.services import ensure_inspections, ensure_pre_rental_orders, ensure_return_orders, refresh_equipment_status


def at(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def approve_inspection(inspection, people, when):
    inspection.result = RentalInspection.Result.APPROVED
    inspection.condition = RentalInspection.Condition.GOOD
    inspection.checklist = [{**row, "status": "OK"} for row in inspection.checklist]
    inspection.performed_by, inspection.performed_at = people["tech"], when
    inspection.observations = "[DEMONSTRAÇÃO] Checklist e teste funcional conferidos."
    inspection.save()
    order = inspection.service_order
    order.status, order.released = ServiceOrder.Status.COMPLETED, True
    order.technician = people["tech"]
    order.final_tests = "[DEMONSTRAÇÃO] Testes funcionais aprovados."
    order.closed_at = when
    order.save()


def create_quote(number, customer, lines, status, people, vehicles, transport=False, ready=False, in_transit=False):
    """Cria o histórico uma vez; reexecutar não desfaz operações feitas pelo testador."""
    if RentalQuote.objects.filter(number=number).exists():
        return
    start, end = min(row[1] for row in lines), max(row[2] for row in lines)
    quote = RentalQuote.objects.create(
        number=number, customer=customer, start_date=start, end_date=end, created_by=people["sales"],
        conditions="[DEMONSTRAÇÃO] Pagamento na devolução. Equipamentos e acessórios conferidos na entrega.",
        notes="Base fictícia para testar o fluxo; não representa uma operação real.",
        delivery_transport_required=transport, return_transport_required=transport,
        delivery_address=customer.address if transport else "", return_address=customer.address if transport else "",
        delivery_number=customer.address_number if transport else "", return_number=customer.address_number if transport else "",
        delivery_cep=customer.address_cep if transport else "", return_cep=customer.address_cep if transport else "",
        requested_delivery_at=at(start, 8), requested_return_at=at(end, 17),
        transport_fee=Decimal("50") if transport else Decimal("0"), estimated_transport_fee=Decimal("50") if transport else Decimal("0"),
    )
    for index, (equipment, first, last, stage) in enumerate(lines):
        destination = {"address": customer.address, "number": str(300+index*10), "cep": customer.address_cep, "complement": "[DEMO] Obra " + str(index+1), "time": f"{8+index*3:02}:00"} if transport and len(lines)>2 else {}
        RentalItem.objects.create(quote=quote, equipment=equipment, start_date=first, end_date=last, daily_rate=equipment.daily_rate, quantity_days=1, delivery_location=destination, return_location=destination)
    quote.recalculate()
    RentalQuote.objects.filter(pk=quote.pk).update(created_at=at(start-timedelta(days=1)))
    if status in {"DRAFT", "SENT", "CANCELLED", "EXPIRED"}:
        quote.status = status
        if status == "CANCELLED":
            quote.cancelled_by, quote.cancelled_at, quote.cancellation_reason = people["sales"], timezone.now(), "[DEMONSTRAÇÃO] Cliente cancelou a obra."
        quote.save()
        return
    quote.status, quote.reserved_by, quote.reserved_at = "APPROVED", people["sales"], at(start-timedelta(days=1))
    quote.save()
    ensure_inspections(quote, "PRE_RENTAL")
    ensure_pre_rental_orders(quote, people["sales"])
    items = list(quote.items.select_related("equipment").order_by("pk"))
    for line, source in zip(items, lines):
        stage = source[3]
        if stage != "PENDING" or ready:
            approve_inspection(quote.inspections.get(equipment=line.equipment, inspection_type="PRE_RENTAL"), people, at(line.start_date, 7))
        line.stage = stage
        if stage != "PENDING":
            line.delivered_at, line.delivered_by = at(line.start_date), people["sales"]
            line.delivery_conditions = "[DEMONSTRAÇÃO] Entrega conferida."
        if stage in {"RETURNED", "COMPLETED"}:
            line.returned_at, line.returned_by = at(line.end_date, 16), people["sales"]
        if stage == "COMPLETED":
            line.finalized_at = at(line.end_date, 17)
        line.save()
    returns = [line for line in items if line.stage in {"RETURNED", "COMPLETED"}]
    if returns:
        ids = [line.equipment_id for line in returns]
        ensure_inspections(quote, "RETURN", equipment_ids=ids)
        ensure_return_orders(quote, people["sales"], equipment_ids=ids)
        for line in returns:
            if line.stage == "COMPLETED":
                approve_inspection(quote.inspections.get(equipment=line.equipment, inspection_type="RETURN"), people, at(line.end_date, 17))
    quote.status = status
    deliveries = [line.delivered_at for line in items if line.delivered_at]
    if deliveries:
        quote.delivered_at, quote.delivered_by = min(deliveries), people["sales"]
    if all(line.stage in {"RETURNED", "COMPLETED"} for line in items):
        quote.returned_at, quote.returned_by = max(line.returned_at for line in items), people["sales"]
    quote.save()
    if transport:
        ensure_transport_task(quote, "DELIVERY", people["sales"], items=items)
        ensure_transport_task(quote, "RETURN", people["sales"], items=[line for line in items if line.stage != "PENDING"])
        for index, task in enumerate(quote.transport_tasks.order_by("pk")):
            selected = list(task_items(task))
            done = all(line.stage != "PENDING" for line in selected) if task.leg == "DELIVERY" else all(line.stage in {"RETURNED", "COMPLETED"} for line in selected)
            task.vehicle, task.driver = list(vehicles.values())[index % len(vehicles)], people["driver"]
            task.status = "COMPLETED" if done else "IN_TRANSIT" if in_transit and index == 0 else "PLANNED"
            if task.status in {"COMPLETED", "IN_TRANSIT"}:
                task.departed_at = task.scheduled_at or at(start)
            if done:
                task.completed_at = task.departed_at + timedelta(minutes=30)
            task.latitude, task.longitude = -22.1757125+.001*(index+1), -47.3820152+.002*(index+1)
            task.geocoded_address = task.address
            task.notes = "[DEMONSTRAÇÃO] Coordenadas ilustrativas; não representam o imóvel informado."
            task.save()


def expand_demo(people, customers, categories, equipment, vehicles, today, stdout):
    from accounts.management.commands.seed_realistic_demo import sample_cpf, sample_cnpj
    from commercial.views import suggest_models_to_buy

    for index in range(6, 19):
        company = index % 2 == 0
        document = sample_cnpj(f"{44000000+index:08d}0001") if company else sample_cpf(f"{540000000+index:09d}")
        customer, _ = Customer.objects.get_or_create(document=document, defaults={
            "person_type": "PJ" if company else "PF", "name": f"Cliente de demonstração {index:02d}" + (" Ltda" if company else ""),
            "email": f"cliente{index}@example.invalid", "phone": f"1999900{index:04d}",
            "address": "Rua Rafael de Barros, Centro, Leme/SP", "address_number": str(100+index*10), "address_cep": "13610000",
            "is_active": index != 18, "marketing_opt_in": index not in (17,18), "notes": "[DEMONSTRAÇÃO] Dados fictícios para testes de cadastro e atendimento.",
        })
        customers[f"extra-{index}"] = customer
    for index, original in enumerate(list(equipment.values())):
        child, _ = EquipmentCategory.objects.get_or_create(name=f"{original.category.name} · Linha profissional", defaults={"parent": original.category, "default_daily_rate": original.daily_rate, "pre_rental_checklist": original.category.pre_rental_checklist, "return_checklist": original.category.return_checklist})
        for unit in range(4):
            code = f"EQ-{7+index*4+unit:03d}"
            item, _ = Equipment.objects.get_or_create(internal_code=code, defaults={"name": original.name, "brand": original.brand, "model": original.model, "serial_number": f"DEMO-EXP-{code}", "category": child, "daily_rate": original.daily_rate+unit*5, "estimated_weight_kg": original.estimated_weight_kg, "current_usage_hours": 50+unit*80, "technical_details": "[DEMONSTRAÇÃO] Unidade adicional para disponibilidade, períodos e paginação."})
            equipment[code] = item
            if not item.media.filter(category="PHOTO").exists():
                photo = original.media.filter(category="PHOTO").first()
                if photo:
                    media = MediaAsset(equipment=item, name=f"Foto demonstrativa · {code}", category="PHOTO", uploaded_by=people["admin"])
                    with photo.file.open("rb") as source:
                        media.file.save(f"{code.lower()}-foto-demo.png", File(source))
    for index in range(4, 13):
        vehicle, _ = Vehicle.objects.get_or_create(plate=f"PDR{index:04d}", defaults={"brand": "Frota demonstrativa", "model": f"Veículo de teste {index}", "vehicle_type": "TRUCK" if index%2 else "VAN", "capacity_kg": 4200 if index%2 else 1500, "status": "MAINTENANCE" if index==11 else "INACTIVE" if index==12 else "AVAILABLE", "notes": "[DEMONSTRAÇÃO] Veículo fictício."})
        if vehicle.status == "AVAILABLE":
            vehicles[f"extra-{index}"] = vehicle
    eq = lambda number: equipment[f"EQ-{number:03d}"]
    day = lambda offset: today+timedelta(days=offset)
    create_quote("ORC-CEN-007", customers["obra"], [(eq(7),day(-2),day(2),"DELIVERED"),(eq(8),day(0),day(4),"PENDING"),(eq(9),day(1),day(5),"PENDING")], "ACTIVE", people, vehicles, transport=True)
    create_quote("ORC-CEN-008", customers["engenharia"], [(eq(10),day(-7),day(-3),"COMPLETED"),(eq(11),day(-6),day(1),"DELIVERED")], "ACTIVE", people, vehicles)
    create_quote("ORC-CEN-009", customers["reforma"], [(eq(12),day(0),day(3),"PENDING"),(eq(13),day(0),day(5),"PENDING")], "APPROVED", people, vehicles, transport=True, ready=True, in_transit=True)
    create_quote("ORC-CEN-010", customers["condominio"], [(eq(14),day(-4),day(-1),"RETURNED")], "RETURNED", people, vehicles)
    damaged = RentalInspection.objects.get(quote__number="ORC-CEN-010", inspection_type="RETURN")
    if damaged.result == "PENDING":
        damaged.result, damaged.condition, damaged.critical_impediment = "BLOCKED", "DAMAGED", True
        damaged.observations = "[DEMONSTRAÇÃO] Proteção avariada no retorno; reparar antes de nova reserva."
        damaged.checklist = [{**entry,"status":"FAIL" if i==0 else "OK"} for i,entry in enumerate(damaged.checklist)]
        damaged.performed_by, damaged.performed_at = people["tech"], timezone.now()
        damaged.save()
        repair=damaged.service_order
        repair.status, repair.priority, repair.technician="IN_PROGRESS","CRÍTICA",people["tech"]
        repair.diagnosis=damaged.observations
        repair.save()
    statuses = ["DRAFT","SENT","APPROVED","ACTIVE","COMPLETED","CANCELLED","EXPIRED","RETURNED"]*2
    for index, status in enumerate(statuses, 11):
        if status in {"COMPLETED","RETURNED"}:
            start,end = -30-index,-25-index
        elif status == "ACTIVE":
            start,end = -3,3
        else:
            start,end = index-9,index-6
        stage = {"ACTIVE":"DELIVERED","COMPLETED":"COMPLETED","RETURNED":"RETURNED"}.get(status,"PENDING")
        customer = list(customers.values())[(index-11)%len(customers)]
        create_quote(f"ORC-CEN-{index:03d}", customer, [(eq(index+4),day(start),day(end),stage)], status, people, vehicles, transport=index%3==0)

    free = [item for item in equipment.values() if not item.rental_items.filter(quote__status__in=["APPROVED","ACTIVE","RETURNED"]).exists()]
    for index, status in enumerate(["OPEN","SCHEDULED","IN_PROGRESS","WAITING_PARTS","ABANDONED","COMPLETED","CANCELLED","OPEN"]):
        order, created = ServiceOrder.objects.get_or_create(number=f"OS-CEN-OFICINA-{index+1:02d}", defaults={
            "equipment": free[index%len(free)], "maintenance_type":"SCHEDULED" if status=="SCHEDULED" else "CORRECTIVE", "status":status,
            "priority":"ALTA" if index%2 else "NORMAL", "symptoms":"[DEMONSTRAÇÃO] Revisar ruído, cabos e proteções.",
            "diagnosis":"[DEMONSTRAÇÃO] Inspeção mecânica em andamento.", "opened_by":people["sales"], "technician":people["tech"],
            "scheduled_at":at(day(3)) if status=="SCHEDULED" else None,
            "abandoned_reason":"[DEMONSTRAÇÃO] Atendimento interrompido para redistribuição." if status=="ABANDONED" else "",
            "released":status=="COMPLETED", "final_tests":"Teste funcional demonstrativo aprovado." if status=="COMPLETED" else "",
        })
        if created:
            MaintenanceActivity.objects.create(service_order=order,description="[DEMONSTRAÇÃO] Conferir proteções e testar funcionamento.",hours=Decimal("0.50"),completed=status=="COMPLETED")
    for index in range(12):
        MaintenancePlan.objects.get_or_create(equipment=free[index%len(free)],name=f"Plano demonstrativo {index+1:02d}",defaults={"maintenance_type":"PREVENTIVE","interval_days":30+index*10,"next_due_date":day(-1 if index==0 else index+5),"criticality":"HIGH" if index==0 else "MEDIUM","checklist":["Conferir fixações","Lubrificar","Teste funcional"]})
    generate_due_preventive_orders(today=today)
    call_command("seed_ai_demo", stdout=stdout)
    for item in equipment.values():
        refresh_equipment_status(item)
    seed_finance(people, customers, today)
    for index in range(12):
        MarketingCampaign.objects.get_or_create(title=f"Campanha de demonstração {index+1:02d}", defaults={"subject":f"[TESTE] Equipamentos para sua obra · {index+1}","body_html":"<h2>Campanha demonstrativa</h2><p>Conteúdo fictício para testar prévia, preparação e filtros. Não enviar a clientes reais.</p>","status":"DRAFT","scheduled_at":at(day(2),9) if index%3==0 else None,"created_by":people["sales"]})
    seed_ai_history(people, equipment)
    for index, category in enumerate(EquipmentCategory.objects.all()):
        for event in range(3):
            UnfulfilledDemand.objects.get_or_create(category=category,notes=f"[DEMO] Pedido não atendido {index}-{event}",defaults={"requested_item":f"Unidade adicional · {category.name}","customer":list(customers.values())[event],"quantity":2,"requested_days":3+event,"expected_daily_rate":category.default_daily_rate,"requested_at":day(-event-1),"recorded_by":people["sales"]})
        quote_items=RentalItem.objects.filter(equipment__category=category).exclude(quote__status__in=["CANCELLED","EXPIRED"])
        orders=ServiceOrder.objects.filter(equipment__category=category).exclude(status="CANCELLED")
        assets=Equipment.objects.filter(category=category)
        models=suggest_models_to_buy(category.pk,quote_items,orders,[],limit=3)
        PurchaseRecommendation.objects.get_or_create(category=category,rationale=f"[DEMONSTRAÇÃO] Reforço de {category.name} com base nos pedidos fictícios registrados.",defaults={"priority":"HIGH" if index%2 else "MEDIUM","current_total":assets.count(),"current_available":assets.filter(status="AVAILABLE").count(),"demand_events":quote_items.values("quote_id").distinct().count(),"maintenance_orders":orders.count(),"suggested_quantity":2,"evidence":{"suggested_equipment":models,"lost_requests":3,"lost_units":6,"lost_customers":3,"limitations":"Base fictícia. Não representa recomendação real de investimento."}})
    for quote in RentalQuote.objects.filter(number__in=["ORC-CEN-004","ORC-CEN-007","ORC-CEN-008"]):
        for kind in ("QUOTE","DELIVERY","RETURN"):
            if kind=="RETURN" and not quote.items.filter(returned_at__isnull=False).exists():
                continue
            if not quote.documents.filter(kind=kind).exists():
                snapshot=snapshot_for(quote,kind)
                RentalDocument.objects.create(quote=quote,kind=kind,version=1,snapshot=snapshot,content_hash=snapshot_hash(snapshot),created_by=people["sales"])


def seed_finance(people, customers, today):
    for quote in RentalQuote.objects.filter(number__startswith="ORC-CEN-",delivered_at__isnull=False):
        if quote.receivables.exists():
            continue
        title=post_quote_receivable(quote,people["sales"])
        if title:
            title.issue_date=timezone.localdate(quote.delivered_at)
            title.save(update_fields=("issue_date",))
    for index, customer in enumerate(customers.values()):
        Receivable.objects.get_or_create(customer=customer,description=f"[DEMO] Serviço complementar {index+1:02d}",defaults={"issue_date":today-timedelta(days=40),"due_date":today+timedelta(days=[-14,-6,-5,0,3,10][index%6]),"amount":Decimal(100+index*15),"created_by":people["sales"]})
    for index in range(14):
        Receivable.objects.get_or_create(customer=customers["obra"],description=f"[DEMO] Faturamento de teste {index+1:02d}",defaults={"issue_date":today-timedelta(days=45),"due_date":today+timedelta(days=index-10),"amount":Decimal(70+index*10),"created_by":people["sales"]})
    for customer, prefix, limit in [(customers["obra"],"[DEMO] Faturamento de teste",3),(customers["engenharia"],"[DEMO] Serviço complementar",1)]:
        key=uuid5(NAMESPACE_URL,f"pandora-demo-pagamento:{customer.document}")
        if Payment.objects.filter(idempotency_key=key).exists():
            continue
        ids=list(customer.receivables.filter(status="OPEN",description__startswith=prefix).order_by("pk").values_list("pk",flat=True)[:limit])
        if ids:
            preview,_=payment_preview(customer.pk,ids,today)
            settle({"customer":customer.pk,"receivable_ids":ids,"payment_date":today,"method":"PIX","notes":"[DEMONSTRAÇÃO] Baixa fictícia; não houve movimentação bancária.","idempotency_key":key,"calculation_token":preview["calculation_token"],"expected_total":Decimal(preview["total"])},people["admin"])


def seed_ai_history(people, equipment):
    for index in range(12):
        text=f"[DEMONSTRAÇÃO {index+1:02d}] Como conferir a manutenção do equipamento?"
        consultation, _=AIConsultation.objects.get_or_create(query_text=text,model="demo-local-sem-llm",defaults={"user":people["tech"],"kind":"MANUAL_QA" if index%2 else "DIAGNOSIS","equipment":list(equipment.values())[index],"status":"DEGRADED","response":{"notice":"Exemplo fictício para testar o histórico; nenhum provedor de IA foi consultado.","analysis":{"answer":"Consulte o manual demonstrativo e confira o checklist com o técnico responsável.","citations":[],"insufficient_data":True},"sources":[],"disclaimer":"Dados de demonstração, sem diagnóstico real."}})
        if index%3==0:
            AIDecision.objects.get_or_create(consultation=consultation,reason="[DEMONSTRAÇÃO] Decisão humana fictícia, sem aplicação na OS.",defaults={"decided_by":people["tech"],"decision":"ACCEPTED","applied_to_order":False})
