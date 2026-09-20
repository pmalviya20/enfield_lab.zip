from flask import Blueprint, request, jsonify

import db
from services.util import log_activity, now_iso

bp = Blueprint("customers", __name__)


@bp.route("/api/customers", methods=["GET"])
def list_customers():
    search = (request.args.get("q") or "").strip()
    sql = "SELECT * FROM customers WHERE 1=1"
    params = []
    if search:
        sql += " AND (name LIKE ? OR phone LIKE ? OR bike_reg_no LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    sql += " ORDER BY name ASC"
    customers = [dict(r) for r in db.query(sql, params)]

    # Attach a quick summary (invoice count, outstanding) - useful for the
    # customers list and avoids N+1 round trips from the frontend.
    for c in customers:
        stats = db.query_one(
            "SELECT COUNT(*) as invoice_count, COALESCE(SUM(total - amount_paid), 0) as outstanding "
            "FROM sales_invoices WHERE customer_id = ?",
            (c["id"],),
        )
        c["invoice_count"] = stats["invoice_count"] if stats else 0
        c["outstanding"] = stats["outstanding"] if stats else 0

    return jsonify({"customers": customers})


@bp.route("/api/customers/<int:customer_id>", methods=["GET"])
def get_customer(customer_id):
    customer = db.query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
    if not customer:
        return jsonify({"error": "Not found"}), 404
    invoices = db.query(
        "SELECT * FROM sales_invoices WHERE customer_id = ? ORDER BY invoice_date DESC, id DESC",
        (customer_id,),
    )
    result = dict(customer)
    result["invoices"] = [dict(i) for i in invoices]
    return jsonify(result)


@bp.route("/api/customers", methods=["POST"])
def create_customer():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    new_id = db.insert_and_get_id(
        "INSERT INTO customers (name, phone, address, bike_reg_no, bike_model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            name,
            (data.get("phone") or "").strip(),
            (data.get("address") or "").strip(),
            (data.get("bike_reg_no") or "").strip().upper(),
            (data.get("bike_model") or "").strip(),
            now_iso(),
        ),
    )
    log_activity("customer", new_id, "created", {"name": name})
    customer = db.query_one("SELECT * FROM customers WHERE id = ?", (new_id,))
    return jsonify(dict(customer)), 201


@bp.route("/api/customers/<int:customer_id>", methods=["PUT"])
def update_customer(customer_id):
    data = request.get_json(force=True, silent=True) or {}
    customer = db.query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
    if not customer:
        return jsonify({"error": "Not found"}), 404

    fields = ["name", "phone", "address", "bike_reg_no", "bike_model"]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if updates:
        params.append(customer_id)
        db.execute(f"UPDATE customers SET {', '.join(updates)} WHERE id = ?", params)
        log_activity("customer", customer_id, "updated", data)

    updated = db.query_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
    return jsonify(dict(updated))
