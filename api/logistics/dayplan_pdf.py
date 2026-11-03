"""PDF do horário do dia (entregas e retiradas por período)."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .dayplan import AFTERNOON, MORNING, PERIOD_LABELS


def _kg(value):
    return "—" if value is None else f"{value:,.1f} kg".replace(",", "X").replace(".", ",").replace("X", ".")


def build_day_plan_pdf(plan, day):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Horário de entregas e retiradas {day:%d/%m/%Y}")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("DayTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=15, leading=18)
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=8, leading=10)
    bold = ParagraphStyle("SmallBold", parent=small, fontName="Helvetica-Bold")
    story = [
        Paragraph("MAZZI DEPÓSITO E MATERIAIS DE CONSTRUÇÃO", title),
        Paragraph(f"HORÁRIO DE ENTREGAS E RETIRADAS — {day:%d/%m/%Y}", styles["Heading2"]),
        Paragraph(f"Saída: {escape(plan['origin']['label'])} · {plan['summary']['deliveries']} entrega(s) · {plan['summary']['pickups']} retirada(s)", small),
        Spacer(1, 4 * mm),
    ]
    vehicles = {v["vehicle"] or 0: v for v in plan["vehicles"]}
    if not plan["stops"]:
        story.append(Paragraph("Nenhuma entrega ou retirada agendada para este dia.", styles["BodyText"]))
    for period in plan["periods"]:
        if not period["stops"]:
            continue
        story.append(Paragraph(f"{period['label'].upper()}", styles["Heading2"]))
        by_vehicle = {}
        for stop in period["stops"]:
            by_vehicle.setdefault(stop["vehicle"] or 0, []).append(stop)
        for vehicle_key, stops in by_vehicle.items():
            vehicle = vehicles.get(vehicle_key, {})
            profile = (vehicle.get("periods") or {}).get(period["key"]) or {}
            driver = next((s["driver_name"] for s in stops if s["driver_name"]), "—")
            story.append(Paragraph(f"Veículo: <b>{escape(vehicle.get('label', 'Sem veículo definido'))}</b> · Motorista: {escape(driver)}", small))
            rows = [["#", "Hora", "Operação", "Cliente / contato", "Endereço", "Equipamentos", "Peso", "OK"]]
            for index, stop in enumerate(stops, 1):
                contact = escape(stop["customer_name"]) + (f"<br/>{escape(stop['customer_phone'])}" if stop["customer_phone"] else "")
                address = escape(stop["address"]) + (f" · {escape(stop['complement'])}" if stop["complement"] else "")
                equipment = "<br/>".join(escape(f"{i['code']} · {i['name']}") for i in stop["items"]) or "—"
                weight = _kg(stop["weight_kg"]) + ("*" if stop["items_without_weight"] else "")
                rows.append([str(index), stop["time"], Paragraph(f"<b>{stop['action_label']}</b><br/>{escape(stop['quote_number'])}", small),
                             Paragraph(contact, small), Paragraph(address, small), Paragraph(equipment, small), weight, "[   ]"])
            table = Table(rows, repeatRows=1, colWidths=[8 * mm, 14 * mm, 28 * mm, 52 * mm, 70 * mm, 62 * mm, 22 * mm, 10 * mm])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243447")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), .4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]))
            story.append(table)
            if profile:
                capacity = vehicle.get("capacity_kg")
                warn = " — <font color='#b91c1c'><b>CARGA ACIMA DA CAPACIDADE</b></font>" if profile.get("overloaded") else ""
                story.append(Spacer(1, 1.5 * mm))
                story.append(Paragraph(
                    f"<b>Peso:</b> sai com {_kg(profile['initial_load_kg'])} (entregas) · retiradas {_kg(profile['pickup_kg'])} · "
                    f"maior carga a bordo {_kg(profile['peak_load_kg'])} · capacidade {_kg(capacity)} · "
                    f"<b>peso ainda disponível: {_kg(profile['remaining_kg'])}</b>{warn}", small))
            story.append(Spacer(1, 4 * mm))
    if any(s["items_without_weight"] for s in plan["stops"]):
        story.append(Paragraph("* Há equipamentos sem peso estimado cadastrado; o peso real pode ser maior.", small))
    story += [Spacer(1, 10 * mm), Paragraph("Responsável pela expedição: ______________________________   Motorista: ______________________________", styles["BodyText"])]
    doc.build(story)
    return buffer.getvalue()
