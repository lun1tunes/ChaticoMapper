"""Security utilities for password hashing and JWT tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from src.core.config import get_settings

password_hash = PasswordHash.recommended()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(plain_password, hashed_password)
    except ValueError:
        # Raised when the stored hash is invalid/corrupted
        return False


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt.expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.security.secret_key, algorithm=settings.jwt.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.security.secret_key, algorithms=[settings.jwt.algorithm])


class TokenDecodeError(Exception):
    """Raised when an access token cannot be decoded."""


def safe_decode_token(token: str) -> dict[str, Any]:
    try:
        return decode_access_token(token)
    except InvalidTokenError as exc:  # pragma: no cover - exception granularity provided by PyJWT
        raise TokenDecodeError(str(exc)) from exc
