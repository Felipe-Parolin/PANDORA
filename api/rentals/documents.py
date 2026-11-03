"""Immutable rental document snapshots and non-fiscal PDF rendering."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import RentalDocument, RentalInspection, RentalItem
from .addresses import full_address, item_destination


INK = colors.HexColor("#1a1c20")
AMBER = colors.HexColor("#f0a500")
MUTED = colors.HexColor("#66686d")
PALE = colors.HexColor("#f4f4f4")


def money(value):
    return f"R$ {Decimal(str(value)):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def snapshot_for(quote, kind):
    customer = quote.customer
    lines = list(quote.items.select_related("equipment", "delivered_by", "returned_by").order_by("equipment__internal_code", "pk"))
    total_items = len(lines)
    if kind == RentalDocument.Kind.DELIVERY:
        lines = [line for line in lines if line.stage != RentalItem.Stage.PENDING]
    elif kind == RentalDocument.Kind.RETURN:
        lines = [line for line in lines if line.stage in {RentalItem.Stage.RETURNED, RentalItem.Stage.COMPLETED}]
    snapshot = {
        "schema_version": 4,
        "partial": len(lines) != total_items,
        "selected_subtotal": str(sum((line.total for line in lines), Decimal("0"))),
        "kind": kind,
        "number": quote.number,
        "customer": {"name": customer.name, "document": customer.document, "phone": customer.phone, "address": full_address(customer.address, customer.address_number)},
        "start_date": quote.start_date.isoformat(),
        "end_date": quote.end_date.isoformat(),
        "items": [{
            "code": line.equipment.internal_code,
            "name": line.equipment.name,
            "model": line.equipment.model,
            "serial_number": line.equipment.serial_number,
            "days": line.quantity_days,
            "daily_rate": str(line.daily_rate),
            "total": str(line.total),
            "start_date": str(line.start_date),
            "end_date": str(line.end_date),
            "stage": line.get_stage_display(),
            "delivered_at": line.delivered_at.isoformat() if line.delivered_at else None,
            "returned_at": line.returned_at.isoformat() if line.returned_at else None,
            "delivered_by": line.delivered_by.full_name if line.delivered_by_id else None,
            "returned_by": line.returned_by.full_name if line.returned_by_id else None,
            "delivery_conditions": line.delivery_conditions,
            "return_conditions": line.return_conditions,
            "destinations": [{"leg": leg, "address": destination['address'], "cep": destination['cep'], "complement": destination['complement'], "scheduled_at": destination['scheduled_at'].isoformat() if destination['scheduled_at'] else None}
                             for leg in ('DELIVERY','RETURN') for destination in [item_destination(quote,line,leg)]],
        } for line in lines],
        "subtotal": str(quote.subtotal),
        "transport_fee": str(quote.transport_fee),
        "estimated_transport_fee": str(quote.estimated_transport_fee),
        "transport_fee_adjustment_reason": quote.transport_fee_adjustment_reason,
        "delivery_transport_required": quote.delivery_transport_required,
        "return_transport_required": quote.return_transport_required,
        "delivery_cep": quote.delivery_cep,
        "return_cep": quote.return_cep,
        "requested_delivery_at": quote.requested_delivery_at.isoformat() if quote.requested_delivery_at else None,
        "requested_return_at": quote.requested_return_at.isoformat() if quote.requested_return_at else None,
        "requested_delivery_notes": quote.requested_delivery_notes,
        "conditions": quote.conditions,
        "discount_percent": str(quote.discount_percent) if quote.discount_percent is not None else None,
        "discount": str(quote.discount),
        "total": str(quote.total),
        "delivery_address": full_address(quote.delivery_address, quote.delivery_number),
        "delivery_complement": quote.delivery_complement,
        "return_address": full_address(quote.return_address, quote.return_number),
        "return_complement": quote.return_complement,
    }
    if kind == RentalDocument.Kind.QUOTE:
        snapshot.update({"status": quote.get_status_display(), "conditions": quote.conditions})
    else:
        is_delivery = kind == RentalDocument.Kind.DELIVERY
        inspections = quote.inspections.filter(
            inspection_type=RentalInspection.Type.PRE_RENTAL if is_delivery else RentalInspection.Type.RETURN,
            equipment_id__in=[line.equipment_id for line in lines],
        ).select_related("equipment", "performed_by").order_by("equipment__internal_code", "pk")
        event_times = [getattr(line, "delivered_at" if is_delivery else "returned_at") for line in lines]
        event_at = max((value for value in event_times if value), default=quote.delivered_at if is_delivery else quote.returned_at)
        last_line = next((line for line in lines if event_at and getattr(line, "delivered_at" if is_delivery else "returned_at") == event_at), None)
        actor_field = "delivered_by" if is_delivery else "returned_by"
        actor = getattr(last_line, actor_field) if last_line else getattr(quote, actor_field)
        snapshot.update({
            "event_at": event_at.isoformat() if event_at else None,
            "event_by": actor.full_name if actor else "Não informado",
            "event_conditions": getattr(last_line or quote, "delivery_conditions" if is_delivery else "return_conditions"),
            "equipment_condition": [{
                "code": item.equipment.internal_code,
                "name": item.equipment.name,
                "status": item.get_result_display(),
                "condition": item.get_condition_display(),
                "observations": item.observations,
                "checklist": item.checklist,
                "critical_impediment": item.critical_impediment,
                "performed_at": item.performed_at.isoformat() if item.performed_at else None,
                "performed_by": item.performed_by.full_name if item.performed_by_id else None,
            } for item in inspections],
        })
        from logistics.services import task_items
        tasks = quote.transport_tasks.filter(leg="DELIVERY" if is_delivery else "RETURN").exclude(status="CANCELLED").select_related("vehicle", "driver")
        line_ids = {line.pk for line in lines}
        snapshot["transport_operations"] = [{
            "status": task.get_status_display(),
            "address": task.address,
            "complement": task.complement,
            "vehicle": task.vehicle.plate if task.vehicle_id else None,
            "driver": task.driver.full_name if task.driver_id else None,
            "departed_at": task.departed_at.isoformat() if task.departed_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "items": [line.equipment.internal_code for line in task_items(task) if line.pk in line_ids],
        } for task in tasks if any(line.pk in line_ids for line in task_items(task))]
    return snapshot


def snapshot_hash(snapshot):
    return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def local_datetime(value):
    if not value:
        return "Não informado"
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    return timezone.localtime(parsed).strftime("%d/%m/%Y %H:%M")


def render_document_pdf(document):
    data = document.snapshot
    output = BytesIO()
    styles = {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=9, leading=13, textColor=MUTED),
        "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=INK, spaceBefore=10, spaceAfter=5, keepWithNext=True),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=13, textColor=INK),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED),
        "right": ParagraphStyle("right", fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=INK, alignment=TA_RIGHT),
    }
    p = lambda value, style="body": Paragraph(escape(str(value if value is not None and value != "" else "-")).replace("\n", "<br/>"), styles[style])
    title = dict(RentalDocument.Kind.choices)[document.kind]
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=19*mm, leftMargin=19*mm, topMargin=18*mm, bottomMargin=19*mm, title=f"PANDORA - {title} {data['number']} v{document.version}", author="PANDORA", lang="pt-BR", invariant=1)
    width = A4[0] - 38*mm
    story = []
    brand = Table([[p("PANDORA", "title"), p("DOCUMENTO NÃO FISCAL", "right")]], colWidths=[width*.64, width*.36])
    brand.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), AMBER), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 11), ("RIGHTPADDING", (0,0), (-1,-1), 11), ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 10)]))
    story.extend([brand, Spacer(1, 14), p(title, "title"), Spacer(1, 4), p(f"{data['number']}  |  Versão {document.version}  |  Gerado em {local_datetime(document.created_at)}", "subtitle")])
    story.extend([p("Cliente", "section"), p(data["customer"]["name"]), p(f"Documento: {data['customer']['document']}  |  Telefone: {data['customer']['phone']}", "small")])
    if data["customer"]["address"]:
        story.append(p(data["customer"]["address"], "small"))
    story.extend([p("Período da locação", "section"), p(f"{data['start_date'][8:10]}/{data['start_date'][5:7]}/{data['start_date'][:4]} a {data['end_date'][8:10]}/{data['end_date'][5:7]}/{data['end_date'][:4]}")])
    equipment_heading = p("Equipamentos", "section")
    # A tabela pode ocupar várias páginas; não deve ser mantida inteira com o título.
    equipment_heading.keepWithNext = False
    story.append(equipment_heading)
    table_rows = [[p("EQUIPAMENTO", "small"), p("DIÁRIAS", "small"), p("VALOR/DIA", "small"), p("TOTAL", "small")]]
    for item in data["items"]:
        period = f"\nPeríodo: {datetime.fromisoformat(item['start_date']):%d/%m/%Y} a {datetime.fromisoformat(item['end_date']):%d/%m/%Y}" if item.get('start_date') else ''
        if data.get('schema_version',1) >= 4:
            for destination in item.get('destinations',[]):
                leg = 'Entrega / retirada' if destination['leg']=='DELIVERY' else 'Coleta / devolução'
                address = destination['address'] if data['delivery_transport_required' if destination['leg']=='DELIVERY' else 'return_transport_required'] else 'Na loja'
                period += f"\n{leg}: {address or 'A combinar'}"
                if destination['complement'] and address != 'Na loja':
                    period += f" - {destination['complement']}"
                if destination['scheduled_at']:
                    period += f" · {local_datetime(destination['scheduled_at'])}"
        events = ''
        if data.get('schema_version', 1) >= 3 and document.kind != RentalDocument.Kind.QUOTE:
            events = f"\nEntrega: {local_datetime(item.get('delivered_at'))} · {item.get('delivered_by') or 'Não informado'}"
            if document.kind == RentalDocument.Kind.RETURN:
                events += f"\nDevolução: {local_datetime(item.get('returned_at'))} · {item.get('returned_by') or 'Não informado'}"
            events += f"\n{item.get('return_conditions') if document.kind == RentalDocument.Kind.RETURN else item.get('delivery_conditions') or ''}"
        table_rows.append([p(f"{item['code']} - {item['name']} ({item['model']})\nSérie: {item['serial_number']}{period}{events}"), p(item["days"]), p(money(item["daily_rate"])), p(money(item["total"]))])
    items_table = Table(table_rows, colWidths=[width*.48, width*.12, width*.19, width*.21], repeatRows=1, hAlign="LEFT")
    items_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), PALE), ("LINEBELOW", (0,0), (-1,0), .6, colors.HexColor("#dedede")), ("LINEBELOW", (0,1), (-1,-1), .25, colors.HexColor("#dedede")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7), ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8)]))
    story.append(items_table)
    discount_label = f"Desconto ({data['discount_percent']}%)" if data["discount_percent"] else "Desconto"
    totals = [[p("Equipamentos"), p(money(data["subtotal"]), "right")], [p("Transporte"), p(money(data["transport_fee"]), "right")], [p(discount_label), p(f"- {money(data['discount'])}", "right")], [p("TOTAL", "right"), p(money(data["total"]), "right")]]
    totals_table = Table(totals, colWidths=[width*.73, width*.27], hAlign="RIGHT", splitByRow=0)
    totals_table.setStyle(TableStyle([("LINEABOVE", (0,3), (-1,3), .9, AMBER), ("BACKGROUND", (0,3), (-1,3), colors.HexColor("#fff8e6")), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    story.extend([Spacer(1, 9), totals_table])
    if data.get('schema_version', 1) >= 3 and document.kind != RentalDocument.Kind.QUOTE:
        story.append(p(f"Registro acumulado {'parcial' if data.get('partial') else 'integral'} das movimentações. Itens deste comprovante: {money(data['selected_subtotal'])}. Os totais acima correspondem ao contrato inteiro; frete e desconto não foram rateados.", 'small'))
    story.append(p(f"Frete estimado: {money(data['estimated_transport_fee'])}. Frete contratado: {money(data['transport_fee'])}.", "small"))
    if data.get("transport_fee_adjustment_reason"):
        story.append(p(f"Justificativa do ajuste: {data['transport_fee_adjustment_reason']}", "small"))
    logistics = []
    if data['delivery_transport_required']:
        logistics.append("entrega contratada")
    if data['return_transport_required']:
        logistics.append("coleta contratada")
    story.append(p("Transporte: " + (" e ".join(logistics) or "retirada e devolução no balcão"), "small"))
    if data.get("requested_delivery_at"):
        story.extend([p("Entrega desejada", "section"), p(local_datetime(data["requested_delivery_at"]))])
    if data.get("requested_delivery_notes"):
        story.append(p(data["requested_delivery_notes"]))
    if data.get("requested_return_at"):
        story.extend([p("Devolução combinada", "section"), p(local_datetime(data["requested_return_at"]))])
    if data.get("conditions"):
        story.extend([p("Condições comerciais", "section"), p(data["conditions"])])
    if document.kind == RentalDocument.Kind.QUOTE:
        story.append(p(f"Situação registrada nesta versão: {data['status']}. Consulte a disponibilidade e o estado atual no sistema.", "small"))
    else:
        event_label = "Entrega" if document.kind == RentalDocument.Kind.DELIVERY else "Devolução"
        event_at = local_datetime(data["event_at"])
        story.extend([p(f"Registro de {event_label.lower()}", "section"), p(f"Data e hora: {event_at}  |  Responsável: {data['event_by']}"), p(data.get("event_conditions") or "Sem observações registradas.")])
        if data["equipment_condition"]:
            story.append(p("Condição dos equipamentos", "section"))
            for item in data["equipment_condition"]:
                story.append(p(f"{item['code']} - {item['name']}: {item['status']} · condição {item['condition']}. {item['observations']}"))
                story.append(p(f"Inspeção: {local_datetime(item['performed_at'])} | Responsável: {item['performed_by'] or 'Não informado'} | Impedimento crítico: {'Sim' if item['critical_impediment'] else 'Não'}", "small"))
                for check in item['checklist']:
                    if isinstance(check, dict):
                        label = check.get('label') or check.get('name') or check.get('id') or 'Item'
                        result = check.get('checked', check.get('value', check.get('status')))
                        result = 'Sim' if result is True else 'Não' if result is False else result
                        result = {'OK': 'Conforme', 'WARNING': 'Ressalva', 'FAIL': 'Falha', 'NA': 'Não se aplica', 'PENDING': 'Pendente'}.get(result, result) if isinstance(result, str) else result
                        detail = check.get('notes') or check.get('observations') or ''
                        story.append(p(f"{label}: {result if result is not None else 'Não informado'} {detail}", "small"))
                    else:
                        story.append(p(check, "small"))
        operations = data.get('transport_operations', [data.get('transport_operation')])
        for operation in filter(None, operations):
            story.extend([p("Transporte registrado", "section"), p(f"{operation['status']} | Veículo: {operation['vehicle'] or '-'} | Motorista: {operation['driver'] or '-'}"), p(f"Saída: {local_datetime(operation['departed_at'])} | Conclusão da viagem: {local_datetime(operation['completed_at'])}"), p(' - '.join(filter(None, [operation['address'], operation['complement']])))])
        story.extend([Spacer(1, 10), p("Comprovante de registro operacional, sem assinatura ou validade fiscal.", "small")])
    if data.get("delivery_address"):
        delivery_address = " - ".join(filter(None, [data["delivery_address"], data["delivery_complement"], f"CEP {data['delivery_cep']}" if data.get("delivery_cep") else None]))
        story.extend([p("Endereço de entrega", "section"), p(delivery_address)])
    if data.get("return_address"):
        return_address = " - ".join(filter(None, [data["return_address"], data["return_complement"], f"CEP {data['return_cep']}" if data.get("return_cep") else None]))
        story.extend([p("Endereço de coleta", "section"), p(return_address)])

    story.append(KeepTogether([Spacer(1, 10), p("Documento comercial/operacional não fiscal, sem assinatura ou validade fiscal.", "small"), p(f"Integridade do snapshot (SHA-256): {document.content_hash}", "small")]))

    def footer(canvas, current_doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dedede"))
        canvas.line(19*mm, 15*mm, A4[0]-19*mm, 15*mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(19*mm, 10*mm, "PANDORA  |  Documento não fiscal")
        canvas.drawRightString(A4[0]-19*mm, 10*mm, f"Página {current_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
