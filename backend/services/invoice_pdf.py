"""Generates a branded, well-aligned customer invoice PDF using reportlab.

Regenerated on demand from the DB each time it's requested (no PDF files
are persisted to disk), so it always reflects the latest payment status
and works fine on hosts with an ephemeral filesystem.
"""
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_PATH = os.path.join(BASE_DIR, "static", "img", "logo_transparent.png")

BRAND_RED = colors.HexColor("#B3141C")
BRAND_BLACK = colors.HexColor("#1a1a1a")
LIGHT_GREY = colors.HexColor("#f2f2f2")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name="BizName", fontSize=18, leading=22, fontName="Helvetica-Bold", textColor=BRAND_BLACK))
    ss.add(ParagraphStyle(name="Small", fontSize=8.5, leading=11, textColor=colors.HexColor("#333333")))
    ss.add(ParagraphStyle(name="SmallRight", fontSize=8.5, leading=11, alignment=TA_RIGHT))
    ss.add(ParagraphStyle(name="InvoiceTitle", fontSize=16, leading=20, fontName="Helvetica-Bold", textColor=BRAND_RED, alignment=TA_RIGHT))
    ss.add(ParagraphStyle(name="TableHeader", fontSize=8.5, leading=10, fontName="Helvetica-Bold", textColor=colors.white))
    ss.add(ParagraphStyle(name="TableCell", fontSize=8.5, leading=10))
    ss.add(ParagraphStyle(name="TableCellRight", fontSize=8.5, leading=10, alignment=TA_RIGHT))
    ss.add(ParagraphStyle(name="TotalsLabel", fontSize=9.5, leading=13, alignment=TA_RIGHT, fontName="Helvetica-Bold"))
    ss.add(ParagraphStyle(name="TotalsValue", fontSize=9.5, leading=13, alignment=TA_RIGHT))
    ss.add(ParagraphStyle(name="GrandTotal", fontSize=12, leading=16, alignment=TA_RIGHT, fontName="Helvetica-Bold", textColor=BRAND_RED))
    ss.add(ParagraphStyle(name="Footer", fontSize=8, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#666666")))
    return ss


def generate_invoice_pdf(invoice: dict, profile: dict) -> bytes:
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        title=f"Invoice {invoice.get('invoice_no', '')}",
    )
    story = []

    # ---- Header: logo + business details on the left, invoice meta on the right ----
    biz_lines = [f"<b>{profile.get('business_name', 'Enfield Lab')}</b>"]
    if profile.get("tagline"):
        biz_lines.append(f"<i>{profile['tagline']}</i>")
    if profile.get("address"):
        biz_lines.append(profile["address"].replace("\n", "<br/>"))
    contact_bits = []
    if profile.get("phone"):
        contact_bits.append(f"Phone: {profile['phone']}")
    if profile.get("email"):
        contact_bits.append(f"Email: {profile['email']}")
    if contact_bits:
        biz_lines.append(" | ".join(contact_bits))
    if profile.get("gstin"):
        biz_lines.append(f"GSTIN: {profile['gstin']}")

    biz_para = Paragraph("<br/>".join(biz_lines), styles["Small"])

    if os.path.exists(LOGO_PATH):
        logo = RLImage(LOGO_PATH, width=20 * mm, height=20 * mm)
    else:
        logo = Spacer(20 * mm, 20 * mm)

    invoice_meta = Paragraph(
        f"TAX INVOICE<br/><font size=9 color='#333333'>Invoice No: <b>{invoice.get('invoice_no','')}</b><br/>"
        f"Date: {invoice.get('invoice_date','')}</font>",
        styles["InvoiceTitle"],
    )

    header_table = Table(
        [[logo, biz_para, invoice_meta]],
        colWidths=[24 * mm, 96 * mm, 62 * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    rule = Table([[""]], colWidths=[182 * mm], rowHeights=[1.2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND_RED)]))
    story.append(rule)
    story.append(Spacer(1, 4 * mm))

    # ---- Bill To ----
    customer = invoice.get("customer") or {}
    bill_lines = [f"<b>Bill To:</b> {customer.get('name', 'Walk-in Customer')}"]
    if customer.get("phone"):
        bill_lines.append(f"Phone: {customer['phone']}")
    if customer.get("address"):
        bill_lines.append(customer["address"])
    bike_bits = []
    if customer.get("bike_model"):
        bike_bits.append(customer["bike_model"])
    if customer.get("bike_reg_no"):
        bike_bits.append(customer["bike_reg_no"])
    if bike_bits:
        bill_lines.append("Vehicle: " + " / ".join(bike_bits))

    story.append(Paragraph("<br/>".join(bill_lines), styles["Small"]))
    story.append(Spacer(1, 5 * mm))

    # ---- Line items table ----
    header = ["#", "Description", "Part No", "Qty", "Rate", "GST%", "GST Amt", "Amount"]
    rows = [[Paragraph(h, styles["TableHeader"]) for h in header]]
    for idx, item in enumerate(invoice.get("items", []), start=1):
        rows.append(
            [
                Paragraph(str(idx), styles["TableCell"]),
                Paragraph(item.get("description") or "", styles["TableCell"]),
                Paragraph(item.get("part_no") or "-", styles["TableCell"]),
                Paragraph(f"{item.get('qty', 0):g}", styles["TableCellRight"]),
                Paragraph(f"{item.get('rate', 0):.2f}", styles["TableCellRight"]),
                Paragraph(f"{item.get('gst_percent', 0):g}%", styles["TableCellRight"]),
                Paragraph(f"{item.get('line_gst_amount', 0):.2f}", styles["TableCellRight"]),
                Paragraph(f"{item.get('line_total', 0):.2f}", styles["TableCellRight"]),
            ]
        )

    col_widths = [8 * mm, 58 * mm, 26 * mm, 12 * mm, 20 * mm, 14 * mm, 20 * mm, 24 * mm]
    items_table = Table(rows, colWidths=col_widths, repeatRows=1)
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLACK),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(items_table)
    story.append(Spacer(1, 5 * mm))

    # ---- Totals ----
    totals_rows = [
        [Paragraph("Subtotal", styles["TotalsLabel"]), Paragraph(f"Rs. {invoice.get('subtotal', 0):.2f}", styles["TotalsValue"])],
        [Paragraph("CGST", styles["TotalsLabel"]), Paragraph(f"Rs. {invoice.get('cgst_amount', 0):.2f}", styles["TotalsValue"])],
        [Paragraph("SGST", styles["TotalsLabel"]), Paragraph(f"Rs. {invoice.get('sgst_amount', 0):.2f}", styles["TotalsValue"])],
        [Paragraph("Total", styles["GrandTotal"]), Paragraph(f"Rs. {invoice.get('total', 0):.2f}", styles["GrandTotal"])],
        [Paragraph("Amount Paid", styles["TotalsLabel"]), Paragraph(f"Rs. {invoice.get('amount_paid', 0):.2f}", styles["TotalsValue"])],
        [
            Paragraph("Balance Due", styles["TotalsLabel"]),
            Paragraph(f"Rs. {invoice.get('total', 0) - invoice.get('amount_paid', 0):.2f}", styles["TotalsValue"]),
        ],
    ]
    totals_table = Table(totals_rows, colWidths=[40 * mm, 40 * mm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(totals_table)
    story.append(Spacer(1, 8 * mm))

    # ---- Bank details / footer ----
    if profile.get("bank_name") or profile.get("bank_account_no"):
        bank_lines = ["<b>Bank Details</b>"]
        if profile.get("bank_name"):
            bank_lines.append(f"Bank: {profile['bank_name']}")
        if profile.get("bank_account_no"):
            bank_lines.append(f"A/C No: {profile['bank_account_no']}")
        if profile.get("bank_ifsc"):
            bank_lines.append(f"IFSC: {profile['bank_ifsc']}")
        story.append(Paragraph("<br/>".join(bank_lines), styles["Small"]))
        story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Thank you for your business! Genuine Royal Enfield parts &amp; service.", styles["Footer"]))

    doc.build(story)
    return buf.getvalue()
