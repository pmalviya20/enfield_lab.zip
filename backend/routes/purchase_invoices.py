from flask import Blueprint, request, jsonify

import db
from services.util import log_activity, now_iso, adjust_stock
from services.pdf_parser import parse_supplier_invoice

bp = Blueprint("purchase_invoices", __name__)


@bp.route("/api/purchase-invoices", methods=["GET"])
def list_purchase_invoices():
    rows = db.query("SELECT * FROM purchase_invoices ORDER BY created_at DESC LIMIT 100")
    return jsonify({"purchase_invoices": [dict(r) for r in rows]})


@bp.route("/api/purchase-invoices/<int:pid>", methods=["GET"])
def get_purchase_invoice(pid):
    invoice = db.query_one("SELECT * FROM purchase_invoices WHERE id = ?", (pid,))
    if not invoice:
        return jsonify({"error": "Not found"}), 404
    items = db.query("SELECT * FROM purchase_invoice_items WHERE purchase_invoice_id = ? ORDER BY sr_no", (pid,))
    result = dict(invoice)
    result["items"] = [dict(i) for i in items]
    return jsonify(result)


@bp.route("/api/purchase-invoices/upload", methods=["POST"])
def upload_purchase_invoice():
    if "file" not in request.files:
        return jsonify({"error": "A PDF file is required (field name 'file')"}), 400

    file = request.files["file"]
    file_bytes = file.read()
    if not file_bytes:
        return jsonify({"error": "Uploaded file is empty"}), 400

    try:
        parsed = parse_supplier_invoice(file_bytes)
    except Exception as e:
        return jsonify({"error": f"Could not read this PDF: {e}"}), 422

    header = parsed["header"]
    line_items = parsed["line_items"]

    invoice_no = header.get("invoice_no")
    invoice_date = header.get("invoice_date")

    if not invoice_no:
        return jsonify({"error": "Could not find an Invoice No. in this PDF - is it a Royal Enfield purchase invoice?"}), 422
    if not line_items:
        return jsonify({"error": "Found the invoice header but no line items could be parsed from the table."}), 422

    # ---- De-duplication: same Invoice No + Invoice Date already uploaded ----
    existing = db.query_one(
        "SELECT * FROM purchase_invoices WHERE invoice_no = ? AND invoice_date = ?",
        (invoice_no, invoice_date),
    )
    if existing:
        return (
            jsonify(
                {
                    "error": "duplicate",
                    "message": f"Invoice {invoice_no} dated {invoice_date} was already uploaded on "
                    f"{existing['created_at']}. This file has not been added again.",
                    "existing_invoice_id": existing["id"],
                }
            ),
            409,
        )

    supplier = db.query_one("SELECT id FROM suppliers ORDER BY id LIMIT 1")
    supplier_id = supplier["id"] if supplier else None

    purchase_invoice_id = db.insert_and_get_id(
        "INSERT INTO purchase_invoices "
        "(supplier_id, invoice_no, invoice_date, order_no, file_name, bill_total, taxable_amount, total_gst, total_mrp, line_item_count, raw_text_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            supplier_id,
            invoice_no,
            invoice_date,
            header.get("order_no"),
            file.filename,
            header.get("bill_total"),
            header.get("taxable_amount"),
            header.get("total_gst"),
            header.get("total_mrp"),
            len(line_items),
            header.get("raw_text_hash"),
            now_iso(),
        ),
    )

    created_items = 0
    updated_items = 0
    total_qty_added = 0.0

    for li in line_items:
        db.execute(
            "INSERT INTO purchase_invoice_items "
            "(purchase_invoice_id, sr_no, part_no, description, hsn_no, mrp, rate, qty, gst_percent, gst_amount, amount, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                purchase_invoice_id,
                li["sr_no"],
                li["part_no"],
                li["description"],
                li["hsn_no"],
                li["mrp"],
                li["rate"],
                li["qty"],
                li["gst_percent"],
                li["gst_amount"],
                li["amount"],
                now_iso(),
            ),
        )

        existing_item = db.query_one("SELECT * FROM inventory_items WHERE part_no = ?", (li["part_no"],))
        if existing_item:
            db.execute(
                "UPDATE inventory_items SET description = ?, hsn_no = ?, mrp = ?, rate = ?, gst_percent = ?, updated_at = ? WHERE id = ?",
                (li["description"], li["hsn_no"], li["mrp"], li["rate"], li["gst_percent"], now_iso(), existing_item["id"]),
            )
            adjust_stock(
                existing_item["id"], li["qty"], reason="purchase", reference_type="purchase_invoice", reference_id=purchase_invoice_id
            )
            updated_items += 1
        else:
            new_id = db.insert_and_get_id(
                "INSERT INTO inventory_items (part_no, description, hsn_no, mrp, rate, gst_percent, stock_qty, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    li["part_no"],
                    li["description"],
                    li["hsn_no"],
                    li["mrp"],
                    li["rate"],
                    li["gst_percent"],
                    li["qty"],
                    now_iso(),
                    now_iso(),
                ),
            )
            db.execute(
                "INSERT INTO stock_movements (inventory_item_id, change_qty, reason, reference_type, reference_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id, li["qty"], "purchase", "purchase_invoice", purchase_invoice_id, now_iso()),
            )
            created_items += 1

        total_qty_added += li["qty"]

    log_activity(
        "purchase_invoice",
        purchase_invoice_id,
        "uploaded",
        {"invoice_no": invoice_no, "created_items": created_items, "updated_items": updated_items},
    )

    return (
        jsonify(
            {
                "ok": True,
                "purchase_invoice_id": purchase_invoice_id,
                "invoice_no": invoice_no,
                "invoice_date": invoice_date,
                "line_items_parsed": len(line_items),
                "inventory_items_created": created_items,
                "inventory_items_updated": updated_items,
                "total_qty_added": total_qty_added,
                "bill_total": header.get("bill_total"),
            }
        ),
        201,
    )
