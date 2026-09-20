# Enfield Lab - production image for Render.
# Docker (not Render's native Python buildpack) is used specifically because
# the barcode/QR "scan to add" OCR fallback needs the tesseract-ocr system
# binary, which a native buildpack can't install.

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Render sets $PORT at runtime; gunicorn binds to it. 2 workers is a sane
# default for the free-tier instance size (512MB RAM).
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60 app:app
