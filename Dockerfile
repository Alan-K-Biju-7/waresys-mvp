FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ✅ OCR system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libglib2.0-0 libsm6 libxrender1 libxext6 \
 && rm -rf /var/lib/apt/lists/*

# ✅ Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy app code
COPY app /app/app

# ✅ Ensure uploads dir exists
RUN mkdir -p /app/uploads

EXPOSE 8000
# CMD is defined in docker-compose.yml
