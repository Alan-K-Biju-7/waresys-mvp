from sqlalchemy import text
from app.db import engine, SessionLocal
from app.auth import get_password_hash
from app import models

def reset_and_seed():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE;"))

    db = SessionLocal()
    try:
        hashed_pw = get_password_hash("admin123")
        admin = models.User(email="admin@waresys.app", hashed_password=hashed_pw, role="admin")
        db.add(admin); db.commit()
        print("✅ Admin user created: admin@waresys.app / admin123")
    finally:
        db.close()

if __name__ == "__main__":
    reset_and_seed()
