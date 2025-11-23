# app/seed_admin.py
from sqlalchemy import select
from app.db import SessionLocal
from app import models
from app.auth import get_password_hash

ADMIN_EMAIL = "admin@waresys.app"
ADMIN_PASSWORD = "admin123"

def ensure_admin() -> None:
    db = SessionLocal()
    try:
        existing = db.execute(
            select(models.User).where(models.User.email == ADMIN_EMAIL)
        ).scalar_one_or_none()

        if existing:
            print(f"✅ Admin user already exists: {ADMIN_EMAIL}")
            return

        admin = models.User(
            email=ADMIN_EMAIL,
            hashed_password=get_password_hash(ADMIN_PASSWORD),
            role="admin",
        )
        db.add(admin)
        db.commit()
        print(f"✅ Admin user created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    finally:
        db.close()
