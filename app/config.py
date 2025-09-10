# api/app/config.py
import os

class Settings:
    def __init__(self):
        self.DATABASE_URL = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://waresys:waresys@db:5432/waresys"
        )
        self.REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")

# for code that does: from app.config import settings
settings = Settings()

# for code that does: from app.config import DATABASE_URL / REDIS_URL / UPLOAD_DIR
DATABASE_URL = settings.DATABASE_URL
REDIS_URL = settings.REDIS_URL
UPLOAD_DIR = settings.UPLOAD_DIR