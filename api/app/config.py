import os
class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL")
    REDIS_URL = os.getenv("REDIS_URL")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key")
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
    OCR_CONF_THRESHOLD = float(os.getenv("OCR_CONF_THRESHOLD", "0.80"))
settings = Settings()
