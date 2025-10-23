import os, logging
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from .db import SessionLocal, init_db
from .config import settings

app = FastAPI(title="Waresys MVP", version="1.0")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
@app.on_event("startup")
def _startup():
    os.makedirs("uploads", exist_ok=True)
    init_db()
