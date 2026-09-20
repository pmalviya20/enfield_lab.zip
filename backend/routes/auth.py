from flask import Blueprint, request, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

import db

bp = Blueprint("auth", __name__)


@bp.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = db.query_one("SELECT * FROM users WHERE username = ?", (username,))
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session.permanent = True
    return jsonify({"id": user["id"], "username": user["username"]})


@bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.route("/api/me")
def me():
    if not session.get("user_id"):
        return jsonify({"error": "not_authenticated"}), 401
    return jsonify({"id": session["user_id"], "username": session["username"]})


@bp.route("/api/change-password", methods=["POST"])
def change_password():
    data = request.get_json(force=True, silent=True) or {}
    current = data.get("current_password") or ""
    new = data.get("new_password") or ""
    if len(new) < 4:
        return jsonify({"error": "New password must be at least 4 characters"}), 400

    user = db.query_one("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    if not check_password_hash(user["password_hash"], current):
        return jsonify({"error": "Current password is incorrect"}), 400

    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new), user["id"]),
    )
    return jsonify({"ok": True})
