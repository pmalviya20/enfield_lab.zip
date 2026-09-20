from flask import Blueprint, request, jsonify

import db
from services.util import log_activity, now_iso

bp = Blueprint("inventory", __name__)


def _item_to_dict(row):
    return dict(row)


@bp.route("/api/inventory", methods=["GET"])
def list_inventory():
    search = (request.args.get("q") or "").strip()
    low_stock_only = request.args.get("low_stock") == "1"
    profile = db.query_one("SELECT low_stock_threshold FROM business_profile LIMIT 1")
    threshold = profile["low_stock_threshold"] if profile else 3

    sql = "SELECT * FROM inventory_items WHERE 1=1"
    params = []
    if search:
        sql += " AND (part_no LIKE ? OR description LIKE ? OR re_model LIKE ? OR barcode LIKE ? OR qr_code LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like, like, like]
    if low_stock_only:
        sql += " AND stock_qty <= ?"
        params.append(threshold)
    sql += " ORDER BY updated_at DESC, id DESC"

    items = [dict(r) for r in db.query(sql, params)]
    return jsonify({"items": items, "low_stock_threshold": threshold})


@bp.route("/api/inventory/<int:item_id>", methods=["GET"])
def get_item(item_id):
    item = db.query_one("SELECT * FROM inventory_items WHERE id = ?", (item_id,))
    if not item:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(item))


@bp.route("/api/inventory/lookup", methods=["GET"])
def lookup_item():
    """Used by the barcode/QR scanner: try to match a scanned code to an
    existing inventory item via part_no, barcode, or qr_code."""
    code = (request.args.get("code") or "").strip()
    if not code:
        return jsonify({"error": "code is required"}), 400
    item = db.query_one(
        "SELECT * FROM inventory_items WHERE part_no = ? OR barcode = ? OR qr_code = ? LIMIT 1",
        (code, code, code),
    )
    if item:
        return jsonify({"found": True, "item": dict(item)})
    return jsonify({"found": False, "scanned_code": code})


@bp.route("/api/inventory", methods=["POST"])
def create_item():
    data = request.get_json(force=True, silent=True) or {}
    part_no = (data.get("part_no") or "").strip()
    description = (data.get("description") or "").strip()
    if not part_no or not description:
        return jsonify({"error": "part_no and description are required"}), 400

    existing = db.query_one("SELECT id FROM inventory_items WHERE part_no = ?", (part_no,))
    if existing:
        return jsonify({"error": f"Part {part_no} already exists in inventory", "existing_id": existing["id"]}), 409

    new_id = db.insert_and_get_id(
        "INSERT INTO inventory_items "
        "(part_no, description, re_model, hsn_no, mrp, rate, gst_percent, stock_qty, barcode, qr_code, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            part_no,
            description,
            data.get("re_model"),
            data.get("hsn_no"),
            float(data.get("mrp") or 0),
            float(data.get("rate") or 0),
            float(data.get("gst_percent") or 0),
            float(data.get("stock_qty") or 0),
            data.get("barcode"),
            data.get("qr_code"),
            now_iso(),
            now_iso(),
        ),
    )
    log_activity("inventory_item", new_id, "created", {"part_no": part_no, "via": data.get("source", "manual")})
    item = db.query_one("SELECT * FROM inventory_items WHERE id = ?", (new_id,))
    return jsonify(dict(item)), 201


@bp.route("/api/inventory/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json(force=True, silent=True) or {}
    item = db.query_one("SELECT * FROM inventory_items WHERE id = ?", (item_id,))
    if not item:
        return jsonify({"error": "Not found"}), 404

    fields = ["part_no", "description", "re_model", "hsn_no", "mrp", "rate", "gst_percent", "stock_qty", "barcode", "qr_code"]
    updates = []
    params = []
    for f in fields:
        if f in data:
            updates.append(f"{f} = ?")
            params.append(data[f])
    if not updates:
        return jsonify(dict(item))
    updates.append("updated_at = ?")
    params.append(now_iso())
    params.append(item_id)
    db.execute(f"UPDATE inventory_items SET {', '.join(updates)} WHERE id = ?", params)
    log_activity("inventory_item", item_id, "updated", data)
    updated = db.query_one("SELECT * FROM inventory_items WHERE id = ?", (item_id,))
    return jsonify(dict(updated))


@bp.route("/api/inventory/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    db.execute("DELETE FROM inventory_items WHERE id = ?", (item_id,))
    log_activity("inventory_item", item_id, "deleted")
    return jsonify({"ok": True})


@bp.route("/api/inventory/scan-ocr", methods=["POST"])
def scan_ocr():
    """Fallback for a part that has no reliable barcode payload: OCR the
    label photo and try to pull out Part No / MRP / description text that's
    printed on Royal Enfield genuine-parts labels."""
    import re
    import pytesseract
    from PIL import Image
    import io

    if "photo" not in request.files:
        return jsonify({"error": "photo file is required"}), 400

    img = Image.open(io.BytesIO(request.files["photo"].read())).convert("RGB")
    # Upscale small phone crops a bit - helps tesseract with small label fonts.
    w, h = img.size
    if max(w, h) < 1600:
        scale = 1600 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)))

    text = pytesseract.image_to_string(img)

    result = {"raw_text": text}

    part_no_match = re.search(r"PART\s*NO[:\s]*([A-Z0-9/\-]{4,})", text, re.IGNORECASE)
    if part_no_match:
        result["part_no"] = part_no_match.group(1).strip().rstrip(".").upper()

    desc_match = re.search(r"PART\s*NO[:\s]*[A-Z0-9/\-]{4,}\s*\n?([A-Z0-9 \-]{4,})", text, re.IGNORECASE)
    if desc_match:
        result["description"] = desc_match.group(1).strip().title()

    mrp_match = re.search(r"MRP\D{0,10}([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if mrp_match:
        result["mrp"] = float(mrp_match.group(1).replace(",", ""))

    qty_match = re.search(r"NET\s*QTY[:\s]*([\d]+)", text, re.IGNORECASE)
    if qty_match:
        result["net_qty"] = int(qty_match.group(1))

    return jsonify(result)
