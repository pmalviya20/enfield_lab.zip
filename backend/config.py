import os
import secrets

# In production (Render) set these as real environment variables.
# Locally, sensible defaults are used so `python app.py` just works.
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "enfield123")
DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB upload cap (invoice PDFs / label photos)

# Google Sign-In (optional). Unset GOOGLE_CLIENT_ID/SECRET = feature hidden,
# username/password login keeps working as before. APP_BASE_URL must match
# the live URL exactly (no trailing slash) - it's used to build the OAuth
# redirect URI, which must also be registered in the Google Cloud Console.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000").rstrip("/")
