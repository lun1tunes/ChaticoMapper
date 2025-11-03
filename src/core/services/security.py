"""Security utilities for password hashing and JWT tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import HasherNotAvailable

from src.core.config import get_settings

logger = logging.getLogger(__name__)

ARGON2_HASHER_AVAILABLE = True

try:
    password_hash = PasswordHash.recommended()
except HasherNotAvailable:
    ARGON2_HASHER_AVAILABLE = False
    password_hash = None  # type: ignore[assignment]
    logger.warning(
        "Argon2 hasher unavailable. Falling back to PBKDF2-SHA256. "
        "Install `pwdlib[argon2]` / `argon2-cffi` for recommended hashing."
    )


class _PBKDF2Fallback:
    """Lightweight PBKDF2 password hasher used when Argon2 is unavailable."""

    algorithm = "pbkdf2_sha256"
    iterations = 390_000
    salt_size = 16

    @staticmethod
    def _b64encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _b64decode(data: str) -> bytes:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(self.salt_size)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.iterations,
        )
        return (
            f"{self.algorithm}"
            f"${self.iterations}"
            f"${self._b64encode(salt)}"
            f"${self._b64encode(derived)}"
        )

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, iter_s, salt_b64, derived_b64 = encoded.split("$")
        except ValueError:
            return False

        if algorithm != self.algorithm:
            return False

        try:
            iterations = int(iter_s)
        except ValueError:
            return False

        salt = self._b64decode(salt_b64)
        expected = self._b64decode(derived_b64)

        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(derived, expected)


_pbkdf2_fallback = _PBKDF2Fallback() if not ARGON2_HASHER_AVAILABLE else None

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="token",
    scopes={
        "me": "Read information about the current user.",
        "admin": "Manage administrative resources.",
    },
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if ARGON2_HASHER_AVAILABLE and password_hash is not None:
        try:
            return password_hash.verify(plain_password, hashed_password)
        except ValueError:
            # Raised when the stored hash is invalid/corrupted
            return False

    # Fallback verification for PBKDF2 hashes
    if not _pbkdf2_fallback:
        raise RuntimeError("PBKDF2 fallback hasher is not initialized")
    return _pbkdf2_fallback.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    if ARGON2_HASHER_AVAILABLE and password_hash is not None:
        return password_hash.hash(password)
    if not _pbkdf2_fallback:
        raise RuntimeError("PBKDF2 fallback hasher is not initialized")
    return _pbkdf2_fallback.hash(password)


def get_password_hash(password: str) -> str:
    return hash_password(password)


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
