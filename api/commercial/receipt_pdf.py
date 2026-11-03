from decimal import Decimal
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from rest_framework.exceptions import ValidationError

from .receivables import digest


def brl(value):
    amount = f"{Decimal(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {amount}"


def date_br(value):
    return "/".join(value.split("-")[::-1])


def render_receipt(payment):
    snapshot = payment.snapshot
    if not snapshot or digest(snapshot) != payment.snapshot_hash:
        raise ValidationError("O registro do recibo não passou pela verificação de integridade.")
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=(210*mm, 297*mm), leftMargin=17*mm, rightMargin=17*mm, topMargin=17*mm, bottomMargin=18*mm, title=f"Recibo {snapshot['number']}", author="PANDORA")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReceiptBody", fontName="Helvetica", fontSize=9, leading=14, textColor=colors.HexColor("#30343a")))
    styles.add(ParagraphStyle(name="ReceiptSmall", parent=styles["ReceiptBody"], fontSize=8, leading=11))
    styles.add(ParagraphStyle(name="ReceiptMoney", parent=styles["ReceiptSmall"], alignment=TA_RIGHT))
    p = lambda text, small=False: Paragraph(escape(str(text)).replace("\n", "<br/>"), styles["ReceiptSmall" if small else "ReceiptBody"])
    customer = snapshot["customer"]
    story = [Paragraph("PANDORA", styles["Heading2"]), Paragraph("Recibo de pagamento", styles["Title"]), p(f"{snapshot['number']}  |  Pagamento em {date_br(snapshot['payment_date'])}  |  {snapshot['method']}"), Spacer(1, 7*mm),
             p(f"Recebemos de {customer['name']}, documento {customer['document']}, a quantia de {brl(snapshot['total'])}, referente exclusivamente às contas relacionadas abaixo."),
             p(" · ".join(filter(None, [customer.get("address"), customer.get("number"), customer.get("cep")]))), Spacer(1, 6*mm)]
    table_rows = [[p("Conta / descrição", True), p("Vencimento", True), p("Principal", True), p("Juros", True), p("Total", True)]]
    for item in snapshot["items"]:
        table_rows.append([p(f"{item['number']}\n{item['description']}", True), p(date_br(item["due_date"]), True), p(brl(item["principal"]), True), p(brl(item["interest"]), True), p(brl(item["total"]), True)])
    table = Table(table_rows, colWidths=[68*mm, 26*mm, 29*mm, 23*mm, 30*mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1efea")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), .7, colors.HexColor("#b8afa0")),
        ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#dedbd5")),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([table, Spacer(1, 6*mm), p(f"Principal: {brl(snapshot['principal'])}     Juros: {brl(snapshot['interest'])}"),
                  Paragraph(f"Total recebido: {brl(snapshot['total'])}", styles["Heading2"]),
                  p("Juros simples, proporcionais por dia (mês de 30 dias), somente após a carência de cada conta. A baixa integral se limita aos títulos discriminados; outras pendências permanecem em aberto.", True)])
    if snapshot.get("notes"):
        story.extend([Spacer(1, 4*mm), p(f"Observações: {snapshot['notes']}")])
    story.extend([Spacer(1, 8*mm), p(f"Registrado por: {snapshot['received_by']}"), p("Assinatura do recebedor: __________________________________________________"), Spacer(1, 5*mm),
                  p("Documento não fiscal. Comprova o pagamento registrado no PANDORA.", True),
                  p(f"Integridade SHA-256: {payment.snapshot_hash}", True)])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(17*mm, 10*mm, snapshot["number"])
        canvas.drawRightString(193*mm, 10*mm, f"Página {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
