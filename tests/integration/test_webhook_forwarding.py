import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
import pytest

from src.core.models.worker_app import WorkerApp


def _instagram_payload(account_id: str, *, comment_id: str | None = None) -> dict:
    from uuid import uuid4

    comment_identifier = comment_id or f"comment-{uuid4()}"
    return {
        "object": "instagram",
        "entry": [
            {
                "id": account_id,
                "time": int(datetime.now(tz=timezone.utc).timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": comment_identifier,
                            "text": "hello",
                            "from": {"id": "user-1", "username": "tester"},
                            "media": {"id": "media-1"},
                        },
                    }
                ],
            }
        ],
    }


def _sign_payload(body: bytes) -> str:
    secret = os.environ["INSTAGRAM_APP_SECRET"]
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def _create_worker_app(db_session, *, account_id: str) -> WorkerApp:
    worker_app = WorkerApp(
        account_id=account_id,
        owner_instagram_username=f"{account_id}_owner",
        base_url=f"https://{account_id}.example/base",
        webhook_url=f"https://{account_id}.example/webhook",
    )
    db_session.add(worker_app)
    await db_session.commit()
    await db_session.refresh(worker_app)
    return worker_app


def _patch_httpx(monkeypatch, capture: dict[str, Any], *, status_code: int = 200, text: str = "", exception: Exception | None = None):
    class _DummyResponse:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

    class _DummyClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            capture["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, *args: Any, **kwargs: Any):
            if exception:
                raise exception
            capture.update({"url": url, "json": kwargs.get("json"), "content": kwargs.get("content"), "headers": dict(kwargs.get("headers") or {})})
            return _DummyResponse(status_code, text)

    monkeypatch.setattr("src.core.use_cases.forward_webhook_use_case.httpx.AsyncClient", _DummyClient)


@pytest.mark.asyncio
async def test_webhook_verification_succeeds(client):
    token = os.environ["WEBHOOK_INIT_VERIFY_TOKEN"]
    response = await client.get(
        "/api/v1/webhook",
        params={"hub.mode": "subscribe", "hub.challenge": "abc123", "hub.verify_token": token},
    )
    assert response.status_code == 200
    assert response.text == "abc123"


@pytest.mark.asyncio
async def test_webhook_verification_rejects_invalid_token(client):
    response = await client.get(
        "/api/v1/webhook",
        params={"hub.mode": "subscribe", "hub.challenge": "nope", "hub.verify_token": "wrong"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_rejects_missing_signature_when_not_in_dev_mode(client, monkeypatch):
    monkeypatch.delenv("DEVELOPMENT_MODE", raising=False)
    payload = json.dumps(_instagram_payload("acct-no-signature")).encode()
    response = await client.post("/api/v1/webhook", content=payload, headers={"content-type": "application/json"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_validation_errors_return_422(client):
    body = json.dumps({"object": "instagram"}).encode()
    response = await client.post(
        "/api/v1/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "X-Hub-Signature-256": _sign_payload(body),
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_returns_failure_when_worker_missing(client):
    account_id = "acct-missing-worker"
    payload = json.dumps(_instagram_payload(account_id)).encode()
    response = await client.post(
        "/api/v1/webhook",
        content=payload,
        headers={
            "content-type": "application/json",
            "X-Hub-Signature-256": _sign_payload(payload),
        },
    )
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["status"] == "failed"
    assert "No worker app found" in resp_json["error_details"]


@pytest.mark.asyncio
async def test_forwarding_keeps_original_headers(client, db_session, monkeypatch):
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")

    worker_app = await _create_worker_app(db_session, account_id="acct-123")
    captured: Dict[str, Any] = {}
    _patch_httpx(monkeypatch, captured)

    payload = _instagram_payload(worker_app.account_id)
    json_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    headers = {
        "content-type": "application/json",
        "authorization": "Bearer abc",
        "x-custom-token": "sample-token",
    }

    response = await client.post(
        "/api/v1/webhook",
        content=json_body,
        headers=headers,
    )

    assert response.status_code == 200
    assert captured["url"] == worker_app.webhook_url
    assert captured["json"] is None
    assert captured["content"] == json_body

    forwarded_headers = {key.lower(): value for key, value in captured["headers"].items()}
    assert forwarded_headers["authorization"] == headers["authorization"]
    assert forwarded_headers["x-custom-token"] == headers["x-custom-token"]
    assert forwarded_headers["content-type"] == "application/json"
    assert forwarded_headers["x-forwarded-from"] == "chatico-mapper"
    assert "host" not in forwarded_headers


@pytest.mark.asyncio
async def test_webhook_success_with_valid_signature_and_forwarding(client, db_session, monkeypatch):
    worker_app = await _create_worker_app(db_session, account_id="acct-signed")
    captured: Dict[str, Any] = {}
    _patch_httpx(monkeypatch, captured, status_code=200)

    payload = json.dumps(_instagram_payload(worker_app.account_id)).encode()
    response = await client.post(
        "/api/v1/webhook",
        content=payload,
        headers={
            "content-type": "application/json",
            "X-Hub-Signature-256": _sign_payload(payload),
        },
    )

    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["status"] == "success"
    assert resp_json["routed_to"] == worker_app.owner_instagram_username
    assert isinstance(resp_json["processing_time_ms"], int) or resp_json["processing_time_ms"] is None
    assert captured["url"] == worker_app.webhook_url


@pytest.mark.asyncio
async def test_webhook_handles_forward_errors(client, db_session, monkeypatch):
    worker_app = await _create_worker_app(db_session, account_id="acct-error")
    captured: Dict[str, Any] = {}
    _patch_httpx(monkeypatch, captured, exception=httpx.TimeoutException("timeout"))

    payload = json.dumps(_instagram_payload(worker_app.account_id)).encode()
    response = await client.post(
        "/api/v1/webhook",
        content=payload,
        headers={
            "content-type": "application/json",
            "X-Hub-Signature-256": _sign_payload(payload),
        },
    )

    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["status"] == "failed"
    assert "Request timeout" in resp_json["error_details"]


@pytest.mark.asyncio
async def test_duplicate_webhook_requests_report_success(client, db_session, monkeypatch):
    worker_app = await _create_worker_app(db_session, account_id="acct-dup")
    captured: Dict[str, Any] = {}
    _patch_httpx(monkeypatch, captured, status_code=200)

    payload_dict = _instagram_payload(worker_app.account_id, comment_id="dup-comment")
    payload = json.dumps(payload_dict).encode()
    headers = {
        "content-type": "application/json",
        "X-Hub-Signature-256": _sign_payload(payload),
    }

    first = await client.post("/api/v1/webhook", content=payload, headers=headers)
    assert first.status_code == 200
    assert first.json()["status"] == "success"

    second = await client.post("/api/v1/webhook", content=payload, headers=headers)
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "success"
    assert body["error_details"] is None
