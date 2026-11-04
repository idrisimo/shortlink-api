import hashlib
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ApiKey

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_key() -> str:
    return f"sl_{secrets.token_urlsafe(32)}"


def create_api_key(db: Session, name: str) -> str:
    """Create and persist a key. The raw value is returned once and never stored."""
    raw = generate_key()
    db.add(ApiKey(name=name, key_hash=hash_key(raw)))
    db.commit()
    return raw


def get_current_key(
    raw_key: str | None = Depends(api_key_header),
    db: Session = Depends(get_db),
) -> ApiKey:
    if not raw_key:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(raw_key)))
    if key is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return key
