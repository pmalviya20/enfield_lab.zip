from flask import Blueprint, request, jsonify

import db
from services.util import log_activity, now_iso

bp = Blueprint("settings", __name__)


@bp.route("/api/settings/profile", methods=["GET"])
def get_profile():
    profile = db.query_one("SELECT * FROM business_profile LIMIT 1")
    return jsonify(dict(profile) if profile else {})


@bp.route("/api/settings/profile", methods=["PUT"])
def update_profile():
    data = request.get_json(force=True, silent=True) or {}
    profile = db.query_one("SELECT * FROM business_profile LIMIT 1")
    if not profile:
        return jsonify({"error": "No profile row found"}), 500

    fields = [
        "business_name",
        "tagline",
        "address",
        "phone",
        "email",
        "gstin",
        "bank_name",
        "bank_account_no",
        "bank_ifsc",
        "invoice_prefix",
        "default_gst_percent",
        "low_stock_threshold",
    ]
    updates, params = [], []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if updates:
        updates.append("updated_at = ?")
        params.append(now_iso())
        params.append(profile["id"])
        db.execute(f"UPDATE business_profile SET {', '.join(updates)} WHERE id = ?", params)
        log_activity("business_profile", profile["id"], "updated", data)

    updated = db.query_one("SELECT * FROM business_profile LIMIT 1")
    return jsonify(dict(updated))


@bp.route("/api/settings/activity", methods=["GET"])
def activity_log():
    limit = int(request.args.get("limit") or 100)
    rows = db.query("SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,))
    return jsonify({"activity": [dict(r) for r in rows]})


@bp.route("/api/settings/google-accounts", methods=["GET"])
def list_google_accounts():
    pending = db.query("SELECT * FROM google_accounts WHERE is_approved = 0 ORDER BY created_at DESC")
    approved = db.query("SELECT * FROM google_accounts WHERE is_approved = 1 ORDER BY approved_at DESC")
    return jsonify({
        "pending": [dict(r) for r in pending],
        "approved": [dict(r) for r in approved],
    })


@bp.route("/api/settings/google-accounts/<int:account_id>/approve", methods=["POST"])
def approve_google_account(account_id):
    account = db.query_one("SELECT * FROM google_accounts WHERE id = ?", (account_id,))
    if not account:
        return jsonify({"error": "Not found"}), 404
    db.execute(
        "UPDATE google_accounts SET is_approved = 1, approved_at = ? WHERE id = ?",
        (now_iso(), account_id),
    )
    log_activity("google_account", account_id, "approved", {"email": account["email"]})
    return jsonify({"ok": True})


@bp.route("/api/settings/google-accounts/<int:account_id>", methods=["DELETE"])
def remove_google_account(account_id):
    account = db.query_one("SELECT * FROM google_accounts WHERE id = ?", (account_id,))
    if not account:
        return jsonify({"error": "Not found"}), 404
    db.execute("DELETE FROM google_accounts WHERE id = ?", (account_id,))
    log_activity("google_account", account_id, "removed", {"email": account["email"]})
    return jsonify({"ok": True})
