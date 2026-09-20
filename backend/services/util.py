import json
from datetime import datetime, timezone

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import config
import db

_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="public-invoice")

PUBLIC_LINK_MAX_AGE = 60 * 60 * 24 * 60  # 60 days


def make_public_invoice_token(invoice_id: int) -> str:
    return _serializer.dumps({"invoice_id": invoice_id})


def verify_public_invoice_token(token: str):
    try:
        data = _serializer.loads(token, max_age=PUBLIC_LINK_MAX_AGE)
        return data.get("invoice_id")
    except (BadSignature, SignatureExpired):
        return None


def whatsapp_share_url(phone: str, message: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits and len(digits) == 10:
        digits = "91" + digits  # assume Indian mobile number without country code
    from urllib.parse import quote

    if digits:
        return f"https://wa.me/{digits}?text={quote(message)}"
    return f"https://wa.me/?text={quote(message)}"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_activity(entity_type, entity_id, action, details=None):
    """Every meaningful write in the app should call this so Settings ->
    Activity / audit trail has a full timestamped record."""
    db.execute(
        "INSERT INTO activity_log (entity_type, entity_id, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (entity_type, entity_id, action, json.dumps(details) if details is not None else None, now_iso()),
    )


def next_sales_invoice_no():
    profile = db.query_one("SELECT * FROM business_profile LIMIT 1")
    prefix = profile["invoice_prefix"] if profile else "INV"
    seq = profile["next_invoice_seq"] if profile else 1
    invoice_no = f"{prefix}-{seq:05d}"
    db.execute(
        "UPDATE business_profile SET next_invoice_seq = ? WHERE id = ?",
        (seq + 1, profile["id"]),
    )
    return invoice_no


def adjust_stock(inventory_item_id, change_qty, reason, reference_type=None, reference_id=None):
    db.execute(
        "UPDATE inventory_items SET stock_qty = stock_qty + ?, updated_at = ? WHERE id = ?",
        (change_qty, now_iso(), inventory_item_id),
    )
    db.execute(
        "INSERT INTO stock_movements (inventory_item_id, change_qty, reason, reference_type, reference_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (inventory_item_id, change_qty, reason, reference_type, reference_id, now_iso()),
    )
