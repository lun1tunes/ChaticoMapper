import pytest
from datetime import datetime, timezone, timedelta

from src.core.services import security


class _DummyHasher:
    """Simple stand-in for Argon2 hasher used in tests."""

    def hash(self, password: str) -> str:
        return f"DUMMY:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        if hashed != f"DUMMY:{password}":
            raise ValueError("invalid hash")
        return True


class _DummyFallback:
    """Stand-in for PBKDF2 fallback implementation."""

    def hash(self, password: str) -> str:
        return f"PBKDF2:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"PBKDF2:{password}"


def test_hash_and_verify_with_argon2(monkeypatch):
    dummy = _DummyHasher()
    monkeypatch.setattr(security, "ARGON2_HASHER_AVAILABLE", True)
    monkeypatch.setattr(security, "password_hash", dummy)

    hashed = security.hash_password("super-secret")
    assert hashed == "DUMMY:super-secret"
    assert security.verify_password("super-secret", hashed) is True


def test_hash_and_verify_with_pbkdf2_fallback(monkeypatch):
    fallback = _DummyFallback()
    monkeypatch.setattr(security, "ARGON2_HASHER_AVAILABLE", False)
    monkeypatch.setattr(security, "password_hash", None)
    monkeypatch.setattr(security, "_pbkdf2_fallback", fallback)

    hashed = security.hash_password("fallback-password")
    assert hashed == "PBKDF2:fallback-password"
    assert security.verify_password("fallback-password", hashed) is True


def test_safe_decode_token_wraps_invalid_token():
    with pytest.raises(security.TokenDecodeError):
        security.safe_decode_token("definitely-not-a-jwt")


def test_create_access_token_and_decode():
    token = security.create_access_token({"sub": "alice"}, expires_delta=timedelta(minutes=1))
    decoded = security.decode_access_token(token)
    assert decoded["sub"] == "alice"
    assert datetime.fromtimestamp(decoded["exp"], tz=timezone.utc) > datetime.now(timezone.utc)
