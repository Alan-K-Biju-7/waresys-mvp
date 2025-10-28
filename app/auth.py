from datetime import datetime, timedelta
import hashlib
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import schemas, models
from app.db import get_db

logger = logging.getLogger(__name__)

# =========================
# Security config (envs)
# =========================
SECRET_KEY = os.getenv("JWT_SECRET", "dev-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("JWT_EXPIRE_MIN") or os.getenv("ACCESS_TOKEN_MINUTES") or "60"
)

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# =========================
# Hashing (matches seeder)
# =========================
def get_password_hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest() == hashed

# =========================
# Token creation
# =========================
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow()

from datetime import datetime, timedelta
import hashlib
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import schemas, models
from app.db import get_db

logger = logging.getLogger(__name__)

# =========================
# Security config (envs)
# =========================
SECRET_KEY = os.getenv("JWT_SECRET", "dev-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("JWT_EXPIRE_MIN") or os.getenv("ACCESS_TOKEN_MINUTES") or "60"
)

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# =========================
# Hashing (matches seeder)
# =========================
def get_password_hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest() == hashed

# =========================
# Token creation
# =========================
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
