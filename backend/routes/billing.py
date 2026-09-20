import io

from flask import Blueprint, request, jsonify, send_file, url_for

import db
from services.util import (
    log_activity,
    now_iso,
    next_sales_invoice_no,
    adjust_stock,
    make_public_invoice_token,
    verify_public_invoice_token,
    whatsapp_share_url,
)
from services.invoice_pdf import generate_invoice_pdf

bp = Blueprint("billing", __name__)


def _invoice_to_dict(invoice_row):
    invoice = dict(invoice_row)
    items = db.query("SELECT * FROM sales_invoice_items WHERE sales_invoice_id = ?", (invoice["id"],))
    invoice["items"] = [dict(i) for i in items]
    if invoice.get("customer_id"):
        customer = db.query_one("SELECT * FROM customers WHERE id = ?", (invoice["customer_id"],))
        invoice["customer"] = dict(customer) if customer else None
    return invoice


@bp.route("/api/invoices", methods=["GET"])
def list_invoices():
    limit = int(request.args.get("limit") or 50)
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    customer_id = request.args.get("customer_id")

    sql = (
        "SELECT si.*, c.name as customer_name, c.phone as customer_phone "
        "FROM sales_invoices si LEFT JOIN customers c ON c.id = si.customer_id WHERE 1=1"
    )
    params = []
    if date_from:
        sql += " AND si.invoice_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND si.invoice_date <= ?"
        params.append(date_to)
    if customer_id:
        sql += " AND si.customer_id = ?"
        params.append(customer_id)
    sql += " ORDER BY si.invoice_date DESC, si.id DESC LIMIT ?"
    params.append(limit)

    invoices = [dict(r) for r in db.query(sql, params)]
    return jsonify({"invoices": invoices})


@bp.route("/api/invoices/<int:invoice_id>", methods=["GET"])
def get_invoice(invoice_id):
    invoice = db.query_one("SELECT * FROM sales_invoices WHERE id = ?", (invoice_id,))
    if not invoice:
        return jsonify({"error": "Not found"}), 404
    return jsonify(_invoice_to_dict(invoice))


@bp.route("/api/invoices", methods=["POST"])
def create_invoice():
    data = request.get_json(force=True, silent=True) or {}
    customer_id = data.get("customer_id")
    invoice_date = data.get("invoice_date") or now_iso()[:10]
    items = data.get("items") or []
    amount_paid = float(data.get("amount_paid") or 0)

    if not items:
        return jsonify({"error": "At least one line item is required"}), 400
    if not customer_id:
        return jsonify({"error": "customer_id is required"}), 400

    customer = db.query_one("SELECT id FROM customers WHERE id = ?", (customer_id,))
    if not customer:
        return jsonify({"error": "Customer not found"}), 404

    subtotal = 0.0
    total_gst = 0.0
    computed_items = []
    for it in items:
        qty = float(it.get("qty") or 0)
        rate = float(it.get("rate") or 0)
        gst_percent = float(it.get("gst_percent") or 0)
        if qty <= 0:
            return jsonify({"error": f"Invalid quantity for {it.get('description', 'item')}"}), 400
        line_subtotal = round(qty * rate, 2)
        line_gst = round(line_subtotal * gst_percent / 100.0, 2)
        line_total = round(line_subtotal + line_gst, 2)
        subtotal += line_subtotal
        total_gst += line_gst
        computed_items.append(
            {
                "inventory_item_id": it.get("inventory_item_id"),
                "description": it.get("description"),
                "part_no": it.get("part_no"),
                "qty": qty,
                "rate": rate,
                "gst_percent": gst_percent,
                "line_subtotal": line_subtotal,
                "line_gst_amount": line_gst,
                "line_total": line_total,
            }
        )

    subtotal = round(subtotal, 2)
    total_gst = round(total_gst, 2)
    cgst = round(total_gst / 2.0, 2)
    sgst = round(total_gst - cgst, 2)
    total = round(subtotal + total_gst, 2)

    invoice_no = next_sales_invoice_no()
    payment_status = "paid" if amount_paid >= total else ("partial" if amount_paid > 0 else "unpaid")

    invoice_id = db.insert_and_get_id(
        "INSERT INTO sales_invoices "
        "(invoice_no, customer_id, invoice_date, subtotal, cgst_amount, sgst_amount, gst_amount, total, amount_paid, payment_status, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            invoice_no,
            customer_id,
            invoice_date,
            subtotal,
            cgst,
            sgst,
            total_gst,
            total,
            amount_paid,
            payment_status,
            data.get("notes"),
            now_iso(),
            now_iso(),
        ),
    )

    for it in computed_items:
        db.execute(
            "INSERT INTO sales_invoice_items "
            "(sales_invoice_id, inventory_item_id, description, part_no, qty, rate, gst_percent, line_subtotal, line_gst_amount, line_total) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                invoice_id,
                it["inventory_item_id"],
                it["description"],
                it["part_no"],
                it["qty"],
                it["rate"],
                it["gst_percent"],
                it["line_subtotal"],
                it["line_gst_amount"],
                it["line_total"],
            ),
        )
        # Deduct stock for items that came from inventory.
        if it["inventory_item_id"]:
            adjust_stock(
                it["inventory_item_id"],
                -it["qty"],
                reason="sale",
                reference_type="sales_invoice",
                reference_id=invoice_id,
            )

    log_activity("sales_invoice", invoice_id, "created", {"invoice_no": invoice_no, "total": total})

    invoice = db.query_one("SELECT * FROM sales_invoices WHERE id = ?", (invoice_id,))
    return jsonify(_invoice_to_dict(invoice)), 201


@bp.route("/api/invoices/<int:invoice_id>/payment", methods=["POST"])
def record_payment(invoice_id):
    data = request.get_json(force=True, silent=True) or {}
    invoice = db.query_one("SELECT * FROM sales_invoices WHERE id = ?", (invoice_id,))
    if not invoice:
        return jsonify({"error": "Not found"}), 404

    amount_paid = float(data.get("amount_paid") if data.get("amount_paid") is not None else invoice["amount_paid"])
    status = "paid" if amount_paid >= invoice["total"] else ("partial" if amount_paid > 0 else "unpaid")
    db.execute(
        "UPDATE sales_invoices SET amount_paid = ?, payment_status = ?, updated_at = ? WHERE id = ?",
        (amount_paid, status, now_iso(), invoice_id),
    )
    log_activity("sales_invoice", invoice_id, "payment_recorded", {"amount_paid": amount_paid})
    updated = db.query_one("SELECT * FROM sales_invoices WHERE id = ?", (invoice_id,))
    return jsonify(_invoice_to_dict(updated))


@bp.route("/api/invoices/<int:invoice_id>/pdf", methods=["GET"])
def invoice_pdf(invoice_id):
    invoice = db.query_one("SELECT * FROM sales_invoices WHERE id = ?", (invoice_id,))
    if not invoice:
        return jsonify({"error": "Not found"}), 404
    invoice_dict = _invoice_to_dict(invoice)
    profile = db.query_one("SELECT * FROM business_profile LIMIT 1")
    pdf_bytes = generate_invoice_pdf(invoice_dict, dict(profile) if profile else {})
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"{invoice_dict['invoice_no']}.pdf",
    )


@bp.route("/api/invoices/<int:invoice_id>/share-link", methods=["GET"])
def invoice_share_link(invoice_id):
    invoice = db.query_one("SELECT * FROM sales_invoices WHERE id = ?", (invoice_id,))
    if not invoice:
        return jsonify({"error": "Not found"}), 404
    invoice_dict = _invoice_to_dict(invoice)
    profile = db.query_one("SELECT * FROM business_profile LIMIT 1")
    business_name = profile["business_name"] if profile else "Enfield Lab"

    token = make_public_invoice_token(invoice_id)
    public_path = f"/api/public/invoices/{token}/pdf"
    public_url = request.host_url.rstrip("/") + public_path

    customer = invoice_dict.get("customer") or {}
    message = (
        f"Hi {customer.get('name', '')}, here is your invoice {invoice_dict['invoice_no']} "
        f"from {business_name} for Rs. {invoice_dict['total']:.2f}. View/download: {public_url}"
    )
    return jsonify(
        {
            "public_url": public_url,
            "whatsapp_url": whatsapp_share_url(customer.get("phone"), message),
        }
    )


@bp.route("/api/public/invoices/<token>/pdf", methods=["GET"])
def public_invoice_pdf(token):
    invoice_id = verify_public_invoice_token(token)
    if not invoice_id:
        return jsonify({"error": "This link is invalid or has expired"}), 404
    invoice = db.query_one("SELECT * FROM sales_invoices WHERE id = ?", (invoice_id,))
    if not invoice:
        return jsonify({"error": "Not found"}), 404
    invoice_dict = _invoice_to_dict(invoice)
    profile = db.query_one("SELECT * FROM business_profile LIMIT 1")
    pdf_bytes = generate_invoice_pdf(invoice_dict, dict(profile) if profile else {})
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"{invoice_dict['invoice_no']}.pdf",
    )
