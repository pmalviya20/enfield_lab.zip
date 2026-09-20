import os
from flask import Flask, send_from_directory, session, jsonify, request
from werkzeug.security import generate_password_hash

import config
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Routes that don't require a logged-in session.
PUBLIC_PATHS = {"/api/login", "/api/health"}
PUBLIC_PREFIXES = ("/static/", "/api/public/")


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static", template_folder="templates")
    app.config.from_object(config)
    app.secret_key = config.SECRET_KEY

    with app.app_context():
        db.init_db()
        _ensure_admin_user()

    from routes.auth import bp as auth_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.inventory import bp as inventory_bp
    from routes.customers import bp as customers_bp
    from routes.billing import bp as billing_bp
    from routes.reports import bp as reports_bp
    from routes.settings import bp as settings_bp
    from routes.purchase_invoices import bp as purchase_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(purchase_bp)

    @app.before_request
    def require_login():
        path = request.path
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES) or not path.startswith("/api/"):
            return None
        if not session.get("user_id"):
            return jsonify({"error": "not_authenticated"}), 401
        return None

    @app.teardown_appcontext
    def close_db(exc):
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            pass  # keep the per-thread sqlite connection open for reuse

    @app.route("/")
    @app.route("/<path:subpath>")
    def spa(subpath=None):
        # Single-page app shell handles all client-side routes (dashboard,
        # billing, inventory, customers, reports, settings).
        return send_from_directory(os.path.join(BASE_DIR, "templates"), "index.html")

    return app


def _ensure_admin_user():
    existing = db.query_one("SELECT id FROM users LIMIT 1")
    if not existing:
        db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (config.ADMIN_USERNAME, generate_password_hash(config.ADMIN_PASSWORD)),
        )


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=config.DEBUG)
