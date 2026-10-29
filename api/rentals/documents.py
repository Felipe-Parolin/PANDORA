"""Immutable rental document snapshots and non-fiscal PDF rendering."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import RentalDocument, RentalInspection


INK = colors.HexColor("#1a1c20")
AMBER = colors.HexColor("#f0a500")
MUTED = colors.HexColor("#66686d")
PALE = colors.HexColor("#f4f4f4")


def money(value):
    return f"R$ {Decimal(str(value)):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def snapshot_for(quote, kind):
    customer = quote.customer
    lines = list(quote.items.select_related("equipment"))
    snapshot = {
        "schema_version": 1,
        "kind": kind,
        "number": quote.number,
        "customer": {"name": customer.name, "document": customer.document, "phone": customer.phone, "address": customer.address},
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
        } for line in lines],
        "subtotal": str(quote.subtotal),
        "transport_fee": str(quote.transport_fee),
        "transport_estimate": quote.transport_estimate,
        "discount_percent": str(quote.discount_percent) if quote.discount_percent is not None else None,
        "discount": str(quote.discount),
        "total": str(quote.total),
        "delivery_address": quote.delivery_address,
        "delivery_complement": quote.delivery_complement,
        "return_address": quote.return_address,
        "return_complement": quote.return_complement,
    }
    if kind == RentalDocument.Kind.QUOTE:
        snapshot.update({"status": quote.get_status_display(), "conditions": quote.conditions})
    else:
        is_delivery = kind == RentalDocument.Kind.DELIVERY
        inspections = quote.inspections.filter(
            inspection_type=RentalInspection.Type.PRE_RENTAL if is_delivery else RentalInspection.Type.RETURN,
            equipment_id__in=[line.equipment_id for line in lines],
        ).select_related("equipment")
        snapshot.update({
            "event_at": (quote.delivered_at if is_delivery else quote.returned_at).isoformat(),
            "event_by": (quote.delivered_by if is_delivery else quote.returned_by).full_name if (quote.delivered_by_id if is_delivery else quote.returned_by_id) else "Não informado",
            "event_conditions": quote.delivery_conditions if is_delivery else quote.return_conditions,
            "equipment_condition": [{
                "code": item.equipment.internal_code,
                "name": item.equipment.name,
                "status": item.get_result_display(),
                "condition": item.get_condition_display(),
                "observations": item.observations,
            } for item in inspections],
        })
    return snapshot


def snapshot_hash(snapshot):
    return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def render_document_pdf(document):
    data = document.snapshot
    output = BytesIO()
    styles = {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=9, leading=13, textColor=MUTED),
        "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=INK, spaceBefore=13, spaceAfter=7),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=13, textColor=INK),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED),
        "right": ParagraphStyle("right", fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=INK, alignment=TA_RIGHT),
    }
    p = lambda value, style="body": Paragraph(escape(str(value or "-")), styles[style])
    title = dict(RentalDocument.Kind.choices)[document.kind]
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=19*mm, leftMargin=19*mm, topMargin=18*mm, bottomMargin=19*mm, title=f"PANDORA - {title} {data['number']} v{document.version}", author="PANDORA", lang="pt-BR")
    width = A4[0] - 38*mm
    story = []
    brand = Table([[p("PANDORA", "title"), p("DOCUMENTO NÃO FISCAL", "right")]], colWidths=[width*.64, width*.36])
    brand.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), AMBER), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 11), ("RIGHTPADDING", (0,0), (-1,-1), 11), ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 10)]))
    story.extend([brand, Spacer(1, 14), p(title, "title"), Spacer(1, 4), p(f"{data['number']}  |  Versão {document.version}  |  Gerado em {document.created_at.astimezone().strftime('%d/%m/%Y %H:%M')}", "subtitle")])
    story.extend([p("Cliente", "section"), p(data["customer"]["name"]), p(f"Documento: {data['customer']['document']}  |  Telefone: {data['customer']['phone']}", "small")])
    if data["customer"]["address"]:
        story.append(p(data["customer"]["address"], "small"))
    story.extend([p("Período da locação", "section"), p(f"{data['start_date'][8:10]}/{data['start_date'][5:7]}/{data['start_date'][:4]} a {data['end_date'][8:10]}/{data['end_date'][5:7]}/{data['end_date'][:4]}")])
    story.append(p("Equipamentos", "section"))
    table_rows = [[p("EQUIPAMENTO", "small"), p("DIÁRIAS", "small"), p("VALOR/DIA", "small"), p("TOTAL", "small")]]
    for item in data["items"]:
        table_rows.append([p(f"{item['code']} - {item['name']} ({item['model']})"), p(item["days"]), p(money(item["daily_rate"])), p(money(item["total"]))])
    items_table = Table(table_rows, colWidths=[width*.48, width*.12, width*.19, width*.21], repeatRows=1, hAlign="LEFT")
    items_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), PALE), ("LINEBELOW", (0,0), (-1,0), .6, colors.HexColor("#dedede")), ("LINEBELOW", (0,1), (-1,-1), .25, colors.HexColor("#dedede")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7), ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8)]))
    story.append(items_table)
    discount_label = f"Desconto ({data['discount_percent']}%)" if data["discount_percent"] else "Desconto"
    totals = [[p("Equipamentos"), p(money(data["subtotal"]), "right")], [p("Transporte"), p(money(data["transport_fee"]), "right")], [p(discount_label), p(f"- {money(data['discount'])}", "right")], [p("TOTAL", "right"), p(money(data["total"]), "right")]]
    totals_table = Table(totals, colWidths=[width*.73, width*.27], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([("LINEABOVE", (0,3), (-1,3), .9, AMBER), ("BACKGROUND", (0,3), (-1,3), colors.HexColor("#fff8e6")), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    story.extend([Spacer(1, 9), totals_table])
    pricing = data.get("transport_estimate") or {}
    legs = [f"{label}: {money(pricing[key]['fee'])}" for key, label in (("delivery", "Entrega"), ("return", "Coleta")) if pricing.get(key)]
    if legs:
        story.append(p("Composição estimada do transporte: " + " + ".join(legs), "small"))
    if document.kind == RentalDocument.Kind.QUOTE:
        if data.get("conditions"):
            story.extend([p("Condições comerciais", "section"), p(data["conditions"]), Spacer(1, 9)])
        story.append(p(f"Situação registrada nesta versão: {data['status']}. Consulte a disponibilidade e o estado atual no sistema.", "small"))
    else:
        event_label = "Entrega" if document.kind == RentalDocument.Kind.DELIVERY else "Devolução"
        event_at = datetime.fromisoformat(data["event_at"]).astimezone().strftime("%d/%m/%Y %H:%M")
        story.extend([p(f"Registro de {event_label.lower()}", "section"), p(f"Data e hora: {event_at}  |  Responsável: {data['event_by']}"), p(data.get("event_conditions") or "Sem observações registradas.")])
        if data["equipment_condition"]:
            story.append(p("Condição dos equipamentos", "section"))
            for item in data["equipment_condition"]:
                story.append(p(f"{item['code']} - {item['name']}: {item['status']} · condição {item['condition']}. {item['observations']}"))
        story.extend([Spacer(1, 10), p("Comprovante de registro operacional, sem assinatura ou validade fiscal.", "small")])
    if data.get("delivery_address"):
        delivery_address = " - ".join(filter(None, [data["delivery_address"], data["delivery_complement"]]))
        story.extend([p("Endereço de entrega", "section"), p(delivery_address)])
    if data.get("return_address"):
        return_address = " - ".join(filter(None, [data["return_address"], data["return_complement"]]))
        story.extend([p("Endereço de coleta", "section"), p(return_address)])

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
