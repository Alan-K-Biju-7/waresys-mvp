# app/Dockerfile (backend API / Celery base)
FROM python:3.11-slim

# --- Python & pip behavior ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# --- System deps for OCR/PDF & runtime tools ---
# - tesseract-ocr + English data
# - poppler-utils for pdf -> images/text
# - lib* for image rendering in pillow/opencv
# - build-essential in case any wheel needs compiling
# - curl for HEALTHCHECK
# - tzdata so logs/timestamps are sane
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng \
    poppler-utils \
    libglib2.0-0 libsm6 libxrender1 libxext6 \
    build-essential \
    curl tzdata \
  && rm -rf /var/lib/apt/lists/*

# --- Python deps (cached layer) ---
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "uvicorn[standard]"

# --- App code ---
COPY app /app/app

# --- Writable dirs (uploads, etc.) ---
RUN mkdir -p /app/uploads

# --- Security: run as non-root ---
RUN useradd -ms /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Optional container healthcheck (expects a /healthz route in FastAPI; adjust if needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/healthz || exit 1

# Default command (docker-compose can override for worker etc.)
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
