import os
import secrets

# In production (Render) set these as real environment variables.
# Locally, sensible defaults are used so `python app.py` just works.
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "enfield123")
DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB upload cap (invoice PDFs / label photos)
