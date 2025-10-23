# app/main.py
import os
import logging
from fastapi import FastAPI

app = FastAPI(title="Waresys MVP", version="1.0")

@app.get("/api/health")
def api_health():
    return {"ok": True, "service": "waresys-api"}
