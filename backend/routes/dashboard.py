from datetime import date

from flask import Blueprint, jsonify

import db

bp = Blueprint("dashboard", __name__)


@bp.route("/api/dashboard", methods=["GET"])
def dashboard():
    today = date.today()
    month_start = today.replace(day=1).isoformat()

    sales_row = db.query_one(
        "SELECT COALESCE(SUM(total), 0) as total FROM sales_invoices WHERE invoice_date >= ?",
        (month_start,),
    )
    sales_this_month = sales_row["total"] if sales_row else 0

    outstanding_row = db.query_one(
        "SELECT COALESCE(SUM(total - amount_paid), 0) as total FROM sales_invoices WHERE payment_status != 'paid'"
    )
    outstanding = outstanding_row["total"] if outstanding_row else 0

    profile = db.query_one("SELECT low_stock_threshold FROM business_profile LIMIT 1")
    threshold = profile["low_stock_threshold"] if profile else 3
    low_stock_row = db.query_one(
        "SELECT COUNT(*) as cnt FROM inventory_items WHERE stock_qty <= ?", (threshold,)
    )
    low_stock_count = low_stock_row["cnt"] if low_stock_row else 0

    customers_row = db.query_one("SELECT COUNT(*) as cnt FROM customers")
    total_customers = customers_row["cnt"] if customers_row else 0

    recent = db.query(
        "SELECT si.*, c.name as customer_name FROM sales_invoices si "
        "LEFT JOIN customers c ON c.id = si.customer_id "
        "ORDER BY si.created_at DESC LIMIT 8"
    )

    return jsonify(
        {
            "sales_this_month": sales_this_month,
            "outstanding_receivables": outstanding,
            "low_stock_items": low_stock_count,
            "total_customers": total_customers,
            "recent_invoices": [dict(r) for r in recent],
        }
    )
