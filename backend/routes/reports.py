from datetime import date, timedelta

from flask import Blueprint, request, jsonify

import db

bp = Blueprint("reports", __name__)


@bp.route("/api/reports/sales", methods=["GET"])
def sales_report():
    date_from = request.args.get("from") or (date.today() - timedelta(days=30)).isoformat()
    date_to = request.args.get("to") or date.today().isoformat()

    summary = db.query_one(
        "SELECT COUNT(*) as invoice_count, COALESCE(SUM(subtotal),0) as subtotal, "
        "COALESCE(SUM(gst_amount),0) as gst_amount, COALESCE(SUM(total),0) as total, "
        "COALESCE(SUM(amount_paid),0) as amount_paid "
        "FROM sales_invoices WHERE invoice_date BETWEEN ? AND ?",
        (date_from, date_to),
    )

    by_status = db.query(
        "SELECT payment_status, COUNT(*) as cnt, COALESCE(SUM(total),0) as total "
        "FROM sales_invoices WHERE invoice_date BETWEEN ? AND ? GROUP BY payment_status",
        (date_from, date_to),
    )

    by_day = db.query(
        "SELECT invoice_date, COUNT(*) as cnt, COALESCE(SUM(total),0) as total "
        "FROM sales_invoices WHERE invoice_date BETWEEN ? AND ? GROUP BY invoice_date ORDER BY invoice_date ASC",
        (date_from, date_to),
    )

    top_parts = db.query(
        "SELECT sii.description, sii.part_no, SUM(sii.qty) as qty_sold, SUM(sii.line_total) as revenue "
        "FROM sales_invoice_items sii "
        "JOIN sales_invoices si ON si.id = sii.sales_invoice_id "
        "WHERE si.invoice_date BETWEEN ? AND ? "
        "GROUP BY sii.description, sii.part_no ORDER BY revenue DESC LIMIT 10",
        (date_from, date_to),
    )

    top_customers = db.query(
        "SELECT c.id, c.name, COUNT(si.id) as invoice_count, COALESCE(SUM(si.total),0) as revenue "
        "FROM sales_invoices si JOIN customers c ON c.id = si.customer_id "
        "WHERE si.invoice_date BETWEEN ? AND ? GROUP BY c.id, c.name ORDER BY revenue DESC LIMIT 10",
        (date_from, date_to),
    )

    return jsonify(
        {
            "from": date_from,
            "to": date_to,
            "summary": dict(summary) if summary else {},
            "by_payment_status": [dict(r) for r in by_status],
            "by_day": [dict(r) for r in by_day],
            "top_parts": [dict(r) for r in top_parts],
            "top_customers": [dict(r) for r in top_customers],
        }
    )


@bp.route("/api/reports/purchases", methods=["GET"])
def purchases_report():
    date_from = request.args.get("from") or (date.today() - timedelta(days=90)).isoformat()
    date_to = request.args.get("to") or date.today().isoformat()

    invoices = db.query(
        "SELECT * FROM purchase_invoices WHERE invoice_date BETWEEN ? AND ? ORDER BY invoice_date DESC",
        (date_from, date_to),
    )
    summary = db.query_one(
        "SELECT COUNT(*) as invoice_count, COALESCE(SUM(bill_total),0) as total_spent, "
        "COALESCE(SUM(total_gst),0) as total_gst "
        "FROM purchase_invoices WHERE invoice_date BETWEEN ? AND ?",
        (date_from, date_to),
    )
    return jsonify(
        {
            "from": date_from,
            "to": date_to,
            "summary": dict(summary) if summary else {},
            "invoices": [dict(r) for r in invoices],
        }
    )
