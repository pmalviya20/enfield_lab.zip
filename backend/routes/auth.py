import secrets
from urllib.parse import urlencode

import requests
from flask import Blueprint, request, jsonify, session, redirect
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
from services.util import log_activity, now_iso

bp = Blueprint("auth", __name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


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

    session.clear()
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
    if session.get("user_id"):
        return jsonify({"id": session["user_id"], "username": session["username"], "auth_type": "local"})
    if session.get("google_account_id"):
        return jsonify({"id": session["google_account_id"], "username": session["username"], "auth_type": "google"})
    return jsonify({"error": "not_authenticated"}), 401


@bp.route("/api/change-password", methods=["POST"])
def change_password():
    if not session.get("user_id"):
        return jsonify({"error": "Password login isn't set up for this account"}), 400

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


@bp.route("/api/auth/google/status")
def google_status():
    return jsonify({"enabled": bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET)})


@bp.route("/api/auth/google/login")
def google_login():
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        return redirect("/?google=error")

    state = secrets.token_urlsafe(24)
    session["google_oauth_state"] = state
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": f"{config.APP_BASE_URL}/api/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
        "access_type": "online",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@bp.route("/api/auth/google/callback")
def google_callback():
    if request.args.get("error"):
        return redirect("/?google=error")

    expected_state = session.pop("google_oauth_state", None)
    state = request.args.get("state")
    if not state or not expected_state or state != expected_state:
        return redirect("/?google=error")

    code = request.args.get("code")
    if not code:
        return redirect("/?google=error")

    try:
        token_res = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": f"{config.APP_BASE_URL}/api/auth/google/callback",
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_res.raise_for_status()
        access_token = token_res.json().get("access_token")
        if not access_token:
            return redirect("/?google=error")

        userinfo_res = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo_res.raise_for_status()
        info = userinfo_res.json()
    except requests.RequestException:
        return redirect("/?google=error")

    email = (info.get("email") or "").strip().lower()
    if not email or not info.get("email_verified"):
        return redirect("/?google=unverified")
    name = info.get("name") or email
    sub = info.get("sub")

    account = db.query_one("SELECT * FROM google_accounts WHERE email = ?", (email,))
    if not account:
        new_id = db.insert_and_get_id(
            "INSERT INTO google_accounts (email, name, google_sub, is_approved, created_at) VALUES (?, ?, ?, ?, ?)",
            (email, name, sub, 0, now_iso()),
        )
        log_activity("google_account", new_id, "signup_requested", {"email": email})
        return redirect("/?google=pending")

    if not account["is_approved"]:
        return redirect("/?google=pending")

    db.execute("UPDATE google_accounts SET name = ?, google_sub = ? WHERE id = ?", (name, sub, account["id"]))

    session.clear()
    session["google_account_id"] = account["id"]
    session["username"] = account["email"]
    session.permanent = True
    log_activity("google_account", account["id"], "login", {"email": email})
    return redirect("/")
