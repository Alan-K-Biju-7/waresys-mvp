import os, logging
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from .db import SessionLocal, init_db
from .config import settings
from typing import List
from fastapi import HTTPException
from . import crud, models, schemas
from .tasks import celery_app
from fastapi import UploadFile, File, Form


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

def _maybe_run_inline_ocr(db: Session, bill: object, file_path: str):
    try:
        from app.ocr_pipeline import process_invoice
        process_invoice(file_path, db, bill.id)
    except Exception as e:
        logging.exception("Inline OCR failed: %s", e)

@app.post("/bills/ocr")
def upload_invoice(
    file: UploadFile = File(...),
    party_name: str | None = Form(None),
    db: Session = Depends(get_db),
):
    dest = os.path.join("uploads", file.filename)
    with open(dest, "wb") as f:
        f.write(file.file.read())
    return {"message": f"Uploaded {file.filename}"}
bash
Copy code
