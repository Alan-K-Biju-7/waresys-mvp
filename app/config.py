# app/config.py
import os

class Settings:
    def __init__(self):
        # The connection string MUST use "+psycopg"
        self.DATABASE_URL = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://waresys:waresys@db:5432/waresys"
        )
        self.REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")

settings = Settings()
DATABASE_URL = settings.DATABASE_URL
REDIS_URL = settings.REDIS_URL
UPLOAD_DIR = settings.UPLOAD_DIR
