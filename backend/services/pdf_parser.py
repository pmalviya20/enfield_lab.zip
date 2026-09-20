"""
Parses the Royal Enfield genuine-parts purchase invoice PDF (as exported by
the RAM Motorcycles / BizErpInvoice portal) and extracts the structured
line-item table plus invoice header fields.

This deliberately does NOT rely on pdfplumber's raw text flow, because the
source PDF wraps long descriptions and part numbers across multiple visual
lines, which merges words together unpredictably in plain text extraction.
Instead it uses pdfplumber's table-grid detection, which correctly keeps
each logical table row's cells together (wrapped text lands inside the same
cell, joined by "\n"). A small number of extra/misaligned None cells show
up on some pages (an artifact of the PDF's underlying grid lines) - those
are simply dropped, which reliably restores the intended 13-column shape.

Verified against a real sample invoice: extracted qty/amount/MRP/GST totals
match the invoice's own printed summary line exactly.
"""
import hashlib
import re

import pdfplumber

EXPECTED_COLUMNS = 13  # sr_no, part_no, description, hsn_no, mrp, rate, qty,
# disc_pct, disc_rs, taxable_amt, gst_pct, gst_amt, amount


def _clean_cell(text):
    if text is None:
        return ""
    return " ".join(text.replace("\n", " ").split())


def _to_float(text):
    text = (text or "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_supplier_invoice(file_bytes: bytes) -> dict:
    full_text_parts = []
    line_items = []

    with pdfplumber.open(file_bytes if hasattr(file_bytes, "read") else __import__("io").BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text_parts.append(text)

            for table in page.extract_tables():
                for row in table:
                    first_cell = (row[0] or "").strip()
                    if not re.fullmatch(r"\d+", first_cell):
                        continue  # not a data row (header / totals / HSN summary)
                    cleaned = [c for c in row if c is not None]
                    if len(cleaned) != EXPECTED_COLUMNS:
                        continue  # unparseable stray row - skip rather than guess
                    (
                        sr_no,
                        part_no,
                        description,
                        hsn_no,
                        mrp,
                        rate,
                        qty,
                        disc_pct,
                        disc_rs,
                        taxable_amt,
                        gst_pct,
                        gst_amt,
                        amount,
                    ) = cleaned
                    line_items.append(
                        {
                            "sr_no": int(sr_no),
                            "part_no": _clean_cell(part_no).replace(" ", ""),
                            "description": _clean_cell(description).title(),
                            "hsn_no": _clean_cell(hsn_no),
                            "mrp": _to_float(mrp),
                            "rate": _to_float(rate),
                            "qty": _to_float(qty),
                            "disc_percent": _to_float(disc_pct),
                            "disc_amount": _to_float(disc_rs),
                            "taxable_amount": _to_float(taxable_amt),
                            "gst_percent": _to_float(gst_pct),
                            "gst_amount": _to_float(gst_amt),
                            "amount": _to_float(amount),
                        }
                    )

    full_text = "\n".join(full_text_parts)

    header = {}
    m = re.search(r"Invoice No\.?\s*:\s*(\S+)\s+Invoice Date\s*:\s*([\d/]+(?:\s+[\d:]+)?)", full_text)
    if m:
        header["invoice_no"] = m.group(1).strip()
        header["invoice_date_raw"] = m.group(2).strip()
        header["invoice_date"] = _normalize_date(header["invoice_date_raw"])

    m = re.search(r"Order No\s*:\s*(\S+)", full_text)
    if m:
        header["order_no"] = m.group(1).strip()

    m = re.search(r"GSTIN\s*:\s*([A-Z0-9]{10,15})", full_text)
    if m:
        header["supplier_gstin"] = m.group(1).strip()

    # Supplier name is the line right after "TAX INVOICE" in this template.
    m = re.search(r"TAX INVOICE\s*\n(.+)", full_text)
    if m:
        header["supplier_name"] = m.group(1).strip()

    m = re.search(r"Bill Total\s+([\d,.]+)", full_text)
    if m:
        header["bill_total"] = _to_float(m.group(1))

    m = re.search(r"Taxable Amount\s+([\d,.]+)", full_text)
    if m:
        header["taxable_amount"] = _to_float(m.group(1))

    m = re.search(r"Total MRP\s+([\d,.]+)", full_text)
    if m:
        header["total_mrp"] = _to_float(m.group(1))

    cgst = re.search(r"CGST\s+([\d,.]+)", full_text)
    sgst = re.search(r"SGST\s+([\d,.]+)", full_text)
    igst = re.search(r"IGST\s+([\d,.]+)", full_text)
    total_gst = 0.0
    if cgst:
        total_gst += _to_float(cgst.group(1))
    if sgst:
        total_gst += _to_float(sgst.group(1))
    if igst:
        total_gst += _to_float(igst.group(1))
    header["total_gst"] = round(total_gst, 2)

    header["raw_text_hash"] = hashlib.sha256(full_text.encode("utf-8", errors="ignore")).hexdigest()
    header["line_item_count"] = len(line_items)

    return {"header": header, "line_items": line_items}


def _normalize_date(raw: str) -> str:
    """'03/09/2026 16:50:09' -> '2026-09-03' (ISO, for sorting/filtering)."""
    date_part = raw.split(" ")[0]
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_part)
    if not m:
        return raw
    day, month, year = m.groups()
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
