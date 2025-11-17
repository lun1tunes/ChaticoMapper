import pytest
import httpx
from sqlalchemy import delete
from uuid import uuid4

from src.core.models.instagram_comment import InstagramComment
from src.core.models.webhook_log import WebhookLog
from src.core.models.worker_app import WorkerApp
from src.core.repositories.webhook_log_repository import WebhookLogRepository
from src.core.use_cases.forward_webhook_use_case import ForwardWebhookUseCase
from src.core.use_cases.process_webhook_use_case import ProcessWebhookUseCase


class _DummyForwardWebhookUseCase:
    def __init__(self, result: dict | None = None):
        self._result = result or {"success": True}
        self.calls: list[dict] = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


class _FakeRedisCacheHit:
    def __init__(self, worker: WorkerApp):
        self.worker = worker
        self.set_calls: list[tuple[str, dict]] = []

    async def get_worker_app(self, account_id: str):
        if account_id == self.worker.account_id:
            return {
                "id": str(self.worker.id),
                "account_id": self.worker.account_id,
                "owner_instagram_username": self.worker.owner_instagram_username,
                "base_url": self.worker.base_url,
                "webhook_url": self.worker.webhook_url,
                "user_id": None,
            }
        return None

    async def set_worker_app(self, account_id: str, worker_app_data: dict, ttl: int | None = None):
        self.set_calls.append((account_id, worker_app_data))
        return True


class _FakeRedisCacheMiss:
    def __init__(self):
        self.set_calls: list[tuple[str, dict]] = []

    async def get_worker_app(self, account_id: str):
        return None

    async def set_worker_app(self, account_id: str, worker_app_data: dict, ttl: int | None = None):
        self.set_calls.append((account_id, worker_app_data))
        return True


async def _truncate_comments(session):
    await session.execute(delete(InstagramComment))
    await session.commit()


def _valid_comment(worker: WorkerApp, *, comment_id: str | None = None) -> dict:
    comment_identifier = comment_id or f"comment-{uuid4()}"
    return {
        "comment_id": comment_identifier,
        "media_id": "media-1",
        "account_id": worker.account_id,
        "user_id": "user-123",
        "username": "tester",
        "text": "hello",
        "parent_id": None,
        "timestamp": 1700000000,
        "raw_data": {"id": comment_id},
    }


async def _create_worker_app(db_session, account_id: str = "acct-process") -> WorkerApp:
    worker = WorkerApp(
        account_id=account_id,
        owner_instagram_username="process-owner",
        base_url="https://worker.example",
        webhook_url="https://worker.example/hook",
    )
    db_session.add(worker)
    await db_session.commit()
    await db_session.refresh(worker)
    return worker


# ============================================================================
# ProcessWebhookUseCase tests
# ============================================================================


@pytest.mark.asyncio
async def test_process_use_case_reports_extraction_error(db_session, monkeypatch):
    await _truncate_comments(db_session)
    dummy_forward = _DummyForwardWebhookUseCase()
    use_case = ProcessWebhookUseCase(db_session, dummy_forward, redis_cache=None)

    def bad_extract(_payload):
        raise ValueError("broken payload")

    monkeypatch.setattr(use_case, "_extract_comments", bad_extract)

    result = await use_case.execute(webhook_payload={})
    assert result["success"] is False
    assert result["errors"] == ["Failed to extract comments: broken payload"]
    assert dummy_forward.calls == []


@pytest.mark.asyncio
async def test_process_use_case_missing_account_id_returns_error(db_session, monkeypatch):
    await _truncate_comments(db_session)
    dummy_forward = _DummyForwardWebhookUseCase()
    use_case = ProcessWebhookUseCase(db_session, dummy_forward, redis_cache=None)

    monkeypatch.setattr(
        use_case,
        "_extract_comments",
        lambda payload: [
            {
                "comment_id": "missing-account",
                "media_id": "media-1",
                "account_id": None,
                "user_id": "user-1",
                "username": "tester",
                "text": "Hello",
                "parent_id": None,
                "timestamp": 1,
                "raw_data": {},
            }
        ],
    )

    result = await use_case.execute(webhook_payload={})
    assert result["success"] is False
    assert "Missing account_id" in result["errors"][0]
    assert dummy_forward.calls == []


@pytest.mark.asyncio
async def test_process_use_case_skips_duplicate_comments(db_session, monkeypatch):
    await _truncate_comments(db_session)
    worker = await _create_worker_app(db_session, account_id="acct-duplicate")

    # Seed existing comment
    existing = InstagramComment(
        comment_id="dup-comment",
        media_id="media-dup",
        owner_id=worker.account_id,
        user_id="user-dup",
        username="tester",
        text="First comment",
        parent_id=None,
        timestamp=1,
        raw_webhook_data={},
    )
    db_session.add(existing)
    await db_session.commit()

    dummy_forward = _DummyForwardWebhookUseCase()
    use_case = ProcessWebhookUseCase(db_session, dummy_forward, redis_cache=None)

    monkeypatch.setattr(use_case, "_extract_comments", lambda payload: [_valid_comment(worker, comment_id="dup-comment")])

    result = await use_case.execute(webhook_payload={})
    assert result["success"] is False
    assert result["comments_processed"] == 0
    assert result["comments_skipped"] == 1
    assert result["errors"] is None
    assert dummy_forward.calls == []


@pytest.mark.asyncio
async def test_process_use_case_uses_redis_cache_hit(db_session, monkeypatch):
    await _truncate_comments(db_session)
    worker = await _create_worker_app(db_session, account_id="acct-cache-hit")
    redis_cache = _FakeRedisCacheHit(worker)
    dummy_forward = _DummyForwardWebhookUseCase()

    use_case = ProcessWebhookUseCase(db_session, dummy_forward, redis_cache=redis_cache)

    async def _fail_get_by_account_id(account_id: str):
        raise AssertionError("Should not query database when cache hits")

    monkeypatch.setattr(use_case.worker_app_repo, "get_by_account_id", _fail_get_by_account_id)
    monkeypatch.setattr(use_case, "_extract_comments", lambda payload: [_valid_comment(worker, comment_id="cache-hit")])

    result = await use_case.execute(webhook_payload={})
    assert result["success"] is True
    assert redis_cache.set_calls == []
    assert len(dummy_forward.calls) == 1


@pytest.mark.asyncio
async def test_process_use_case_populates_cache_on_miss(db_session, monkeypatch):
    await _truncate_comments(db_session)
    worker = await _create_worker_app(db_session, account_id="acct-cache-miss")
    redis_cache = _FakeRedisCacheMiss()
    dummy_forward = _DummyForwardWebhookUseCase()

    use_case = ProcessWebhookUseCase(db_session, dummy_forward, redis_cache=redis_cache)
    monkeypatch.setattr(use_case, "_extract_comments", lambda payload: [_valid_comment(worker, comment_id="cache-miss")])

    result = await use_case.execute(webhook_payload={})
    assert result["success"] is True
    assert len(redis_cache.set_calls) == 1
    cache_account_id, payload = redis_cache.set_calls[0]
    assert cache_account_id == worker.account_id
    assert payload["id"] == str(worker.id)


@pytest.mark.asyncio
async def test_process_use_case_rolls_back_and_continues_on_store_failure(db_session, monkeypatch):
    await _truncate_comments(db_session)
    worker = await _create_worker_app(db_session, account_id="acct-rollback")
    dummy_forward = _DummyForwardWebhookUseCase()
    use_case = ProcessWebhookUseCase(db_session, dummy_forward, redis_cache=None)

    async def failing_store(_comment_data):
        raise RuntimeError("db failure")

    monkeypatch.setattr(use_case, "_extract_comments", lambda payload: [_valid_comment(worker, comment_id="store-failure")])
    monkeypatch.setattr(use_case, "_store_comment", failing_store)

    from unittest.mock import AsyncMock

    fake_rollback = AsyncMock()
    monkeypatch.setattr(use_case.session, "rollback", fake_rollback)

    result = await use_case.execute(webhook_payload={})
    assert result["success"] is True
    assert fake_rollback.await_count == 1
    assert len(dummy_forward.calls) == 1


@pytest.mark.asyncio
async def test_process_use_case_handles_forward_failure(db_session, monkeypatch):
    await _truncate_comments(db_session)
    worker = await _create_worker_app(db_session, account_id="acct-forward-fail")
    dummy_forward = _DummyForwardWebhookUseCase(
        result={
            "success": False,
            "error": "Request timeout",
        }
    )
    use_case = ProcessWebhookUseCase(db_session, dummy_forward, redis_cache=None)

    monkeypatch.setattr(use_case, "_extract_comments", lambda payload: [_valid_comment(worker, comment_id="forward-failure")])

    result = await use_case.execute(webhook_payload={})
    assert result["success"] is False
    assert "Request timeout" in (result["errors"][0])
    assert len(dummy_forward.calls) == 1


# ============================================================================
# ForwardWebhookUseCase tests
# ============================================================================


def _stub_httpx_client(monkeypatch, *, response_status: int = 200, response_text: str = "", exception: Exception | None = None, capture: dict | None = None):
    class _DummyResponse:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            if capture is not None:
                capture["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, **kwargs):
            if capture is not None:
                capture["url"] = url
                capture["kwargs"] = kwargs
            if exception:
                raise exception
            return _DummyResponse(response_status, response_text)

    monkeypatch.setattr("src.core.use_cases.forward_webhook_use_case.httpx.AsyncClient", _FakeClient)


@pytest.mark.asyncio
async def test_forward_use_case_success_logs_entry(db_session, monkeypatch):
    await db_session.execute(delete(WebhookLog))
    await db_session.commit()

    worker = await _create_worker_app(db_session, account_id="acct-forward-success")
    _stub_httpx_client(monkeypatch, response_status=200)

    use_case = ForwardWebhookUseCase(db_session)
    result = await use_case.execute(worker_app=worker, webhook_payload={}, account_id=worker.account_id)
    assert result["success"] is True

    repo = WebhookLogRepository(db_session)
    logs = await repo.get_by_account_id(worker.account_id)
    assert len(logs) == 1
    assert logs[0].status == "success"


@pytest.mark.asyncio
async def test_forward_use_case_http_error_logged_as_failure(db_session, monkeypatch):
    await db_session.execute(delete(WebhookLog))
    await db_session.commit()

    worker = await _create_worker_app(db_session, account_id="acct-forward-error")
    _stub_httpx_client(monkeypatch, response_status=500, response_text="boom")

    use_case = ForwardWebhookUseCase(db_session)
    result = await use_case.execute(worker_app=worker, webhook_payload={}, account_id=worker.account_id)
    assert result["success"] is False
    assert result["error"] == "Worker app returned 500"

    repo = WebhookLogRepository(db_session)
    logs = await repo.get_by_account_id(worker.account_id)
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].error_message == "Worker app returned 500"


@pytest.mark.asyncio
async def test_forward_use_case_handles_timeout(db_session, monkeypatch):
    await db_session.execute(delete(WebhookLog))
    await db_session.commit()

    worker = await _create_worker_app(db_session, account_id="acct-forward-timeout")
    _stub_httpx_client(monkeypatch, exception=httpx.TimeoutException("timeout"))

    use_case = ForwardWebhookUseCase(db_session)
    result = await use_case.execute(worker_app=worker, webhook_payload={}, account_id=worker.account_id)
    assert result["success"] is False
    assert result["error"] == "Request timeout"

    repo = WebhookLogRepository(db_session)
    logs = await repo.get_by_account_id(worker.account_id)
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].error_message == "Request timeout"


@pytest.mark.asyncio
async def test_forward_use_case_filters_headers(db_session, monkeypatch):
    worker = await _create_worker_app(db_session, account_id="acct-forward-headers")
    capture: dict = {}
    _stub_httpx_client(monkeypatch, response_status=200, capture=capture)

    use_case = ForwardWebhookUseCase(db_session)
    raw_payload = b'{"entry":[]}'
    result = await use_case.execute(
        worker_app=worker,
        webhook_payload={"entry": []},
        account_id=worker.account_id,
        original_headers={
            "Content-Type": "application/json",
            "Host": "instagram.com",
            "X-Custom": "keep-me",
        },
        raw_payload=raw_payload,
    )
    assert result["success"] is True

    forwarded_headers = capture["kwargs"]["headers"]
    assert "Host" not in forwarded_headers
    assert forwarded_headers["Content-Type"] == "application/json"
    assert forwarded_headers["X-Custom"] == "keep-me"
    assert forwarded_headers["X-Forwarded-From"] == "chatico-mapper"
    assert "X-Webhook-ID" in forwarded_headers
    assert capture["kwargs"]["content"] == raw_payload
    assert capture["kwargs"].get("json") is None
