import os, logging
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from .db import SessionLocal, init_db
from .config import settings
from typing import List
from fastapi import HTTPException
from . import crud, models, schemas
from .tasks import celery_app


TASK_NAME = os.getenv("OCR_TASK_NAME", "app.tasks.process_invoice")
OCR_SYNC = os.getenv("OCR_SYNC", "0") == "1"
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

@app.post("/products", response_model=schemas.ProductOut)
def create_product(p: schemas.ProductIn, db: Session = Depends(get_db)):
    return crud.create_product(db, **p.model_dump())

@app.get("/products", response_model=List[schemas.ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(models.Product).limit(50).all()

