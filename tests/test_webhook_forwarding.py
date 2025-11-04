from datetime import datetime, timezone
import json
from typing import Any, Dict

import httpx
import pytest

from src.api_v1.schemas import WebhookPayload
from src.core.models.worker_app import WorkerApp


@pytest.mark.asyncio
async def test_forwarding_keeps_original_headers(client, db_session, monkeypatch):
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")

    worker_app = WorkerApp(
        account_id="acct-123",
        owner_instagram_username="owneruser",
        base_url="https://worker.example",
        webhook_url="https://worker.example/webhook",
    )
    db_session.add(worker_app)
    await db_session.commit()

    captured: Dict[str, Any] = {}

    class _DummyResponse:
        status_code = 200
        text = ""

    class _DummyClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, *args: Any, **kwargs: Any) -> _DummyResponse:
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            captured["content"] = kwargs.get("content")
            captured["headers"] = dict(kwargs.get("headers") or {})
            return _DummyResponse()

    monkeypatch.setattr(
        "src.core.use_cases.forward_webhook_use_case.httpx.AsyncClient",
        _DummyClient,
    )

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": worker_app.account_id,
                "time": int(datetime.now(tz=timezone.utc).timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment-1",
                            "text": "hello",
                            "from": {"id": "user-1", "username": "tester"},
                            "media": {"id": "media-1"},
                        },
                    }
                ],
            }
        ],
    }

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
