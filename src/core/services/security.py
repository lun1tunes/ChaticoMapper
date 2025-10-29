"""Security utilities for password hashing and JWT tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.jwt.expire_minutes))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.security.secret_key, algorithm=settings.jwt.algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.security.secret_key, algorithms=[settings.jwt.algorithm])


class TokenDecodeError(Exception):
    """Raised when an access token cannot be decoded."""


def safe_decode_token(token: str) -> dict[str, Any]:
    try:
        return decode_access_token(token)
    except JWTError as exc:  # pragma: no cover – jose provides limited exception granularity
        raise TokenDecodeError(str(exc)) from exc
