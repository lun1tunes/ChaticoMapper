import pytest
from uuid import uuid4

from src.core.models.instagram_comment import InstagramComment
from src.core.models.user import User, UserRole
from src.core.models.webhook_log import WebhookLog
from src.core.models.worker_app import WorkerApp
from src.core.repositories.instagram_comment_repository import InstagramCommentRepository
from src.core.repositories.user_repository import UserRepository
from src.core.repositories.webhook_log_repository import WebhookLogRepository
from src.core.repositories.worker_app_repository import WorkerAppRepository
from src.core.services.security import hash_password


@pytest.mark.asyncio
async def test_worker_app_repository_operations(db_session):
    from sqlalchemy import delete

    repo = WorkerAppRepository(db_session)

    await db_session.execute(delete(WorkerApp))
    await db_session.commit()

    user = User(
        username="repo_user",
        full_name="Repo User",
        hashed_password=hash_password("password-1"),
        role=UserRole.ADMIN.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    worker_with_user = WorkerApp(
        account_id="acct-worker-1",
        owner_instagram_username="worker1",
        base_url="https://worker1.example",
        webhook_url="https://worker1.example/hook",
        user_id=user.id,
    )
    worker_without_user = WorkerApp(
        account_id="acct-worker-2",
        owner_instagram_username="worker2",
        base_url="https://worker2.example",
        webhook_url="https://worker2.example/hook",
    )

    await repo.create(worker_with_user)
    await repo.create(worker_without_user)
    await db_session.commit()

    fetched = await repo.get_by_account_id("acct-worker-1")
    assert fetched is not None
    assert fetched.owner_instagram_username == "worker1"

    fetched_by_user = await repo.get_by_user_id(user.id)
    assert fetched_by_user is not None
    assert fetched_by_user.account_id == worker_with_user.account_id

    assert await repo.exists_by_account_id("acct-worker-1") is True
    assert await repo.exists_by_account_id("missing-acct") is False

    all_workers = await repo.get_all(limit=10, offset=0)
    assert {w.account_id for w in all_workers} == {"acct-worker-1", "acct-worker-2"}

    await repo.delete(worker_without_user)
    await db_session.commit()
    assert await repo.get_by_account_id("acct-worker-2") is None


@pytest.mark.asyncio
async def test_instagram_comment_repository_queries(db_session):
    repo = InstagramCommentRepository(db_session)

    parent_comment = InstagramComment(
        comment_id="comment-parent",
        media_id="media-1",
        owner_id="acct-comments",
        user_id="user-commenter",
        username="commenter",
        text="Parent comment",
        parent_id=None,
        timestamp=1,
        raw_webhook_data={"field": "value"},
    )
    reply_comment = InstagramComment(
        comment_id="comment-reply",
        media_id="media-1",
        owner_id="acct-comments",
        user_id="user-replier",
        username="replier",
        text="Reply comment",
        parent_id="comment-parent",
        timestamp=2,
        raw_webhook_data={"field": "value"},
    )
    another_comment_same_user = InstagramComment(
        comment_id="comment-second",
        media_id="media-2",
        owner_id="acct-comments",
        user_id="user-commenter",
        username="commenter",
        text="Second comment",
        parent_id=None,
        timestamp=3,
        raw_webhook_data={"field": "value"},
    )
    db_session.add_all([parent_comment, reply_comment, another_comment_same_user])
    await db_session.commit()

    fetched = await repo.get_by_comment_id("comment-parent")
    assert fetched is not None
    assert fetched.text == "Parent comment"

    by_user = await repo.get_by_user_id("user-commenter")
    assert {c.comment_id for c in by_user} == {"comment-parent", "comment-second"}

    replies = await repo.get_replies("comment-parent")
    assert len(replies) == 1
    assert replies[0].comment_id == "comment-reply"

    assert await repo.exists_by_comment_id("comment-second") is True
    assert await repo.exists_by_comment_id("non-existent") is False


@pytest.mark.asyncio
async def test_user_repository_lookup(db_session):
    repo = UserRepository(db_session)

    user = User(
        username="lookup_user",
        full_name="Lookup User",
        hashed_password=hash_password("password"),
        role=UserRole.BASIC.value,
    )
    db_session.add(user)
    await db_session.commit()

    fetched = await repo.get_by_username("lookup_user")
    assert fetched is not None
    assert fetched.username == "lookup_user"

    assert await repo.get_by_username("missing-user") is None


@pytest.mark.asyncio
async def test_webhook_log_repository_queries(db_session):
    from sqlalchemy import delete

    await db_session.execute(delete(WebhookLog))
    await db_session.commit()

    worker_repo = WorkerAppRepository(db_session)
    log_repo = WebhookLogRepository(db_session)

    worker = WorkerApp(
        account_id="acct-logs",
        owner_instagram_username="logowner",
        base_url="https://log.example",
        webhook_url="https://log.example/hook",
    )
    await worker_repo.create(worker)
    await db_session.commit()
    await db_session.refresh(worker)

    success_log = WebhookLog(
        webhook_id="log-success",
        account_id="acct-logs",
        worker_app_id=worker.id,
        target_owner_username="logowner",
        target_base_url=worker.webhook_url,
        status="success",
        processing_time_ms=123,
    )
    failed_log = WebhookLog(
        webhook_id="log-failed",
        account_id="acct-logs",
        worker_app_id=worker.id,
        target_owner_username="logowner",
        target_base_url=worker.webhook_url,
        status="failed",
        error_message="timeout",
        processing_time_ms=456,
    )

    db_session.add_all([success_log, failed_log])
    await db_session.commit()

    assert (await log_repo.get_by_webhook_id("log-success")).status == "success"
    assert await log_repo.get_by_webhook_id("missing-log") is None

    by_account = await log_repo.get_by_account_id("acct-logs")
    assert {log.webhook_id for log in by_account} == {"log-success", "log-failed"}

    by_worker = await log_repo.get_by_worker_app_id(worker.id)
    assert len(by_worker) == 2

    failed_logs = await log_repo.get_by_status("failed")
    assert len(failed_logs) == 1
    assert failed_logs[0].webhook_id == "log-failed"

    assert await log_repo.count_by_status("failed") == 1
    assert await log_repo.count_by_account_id("acct-logs") == 2
    assert len(await log_repo.get_failed_logs()) == 1

    assert await log_repo.exists_by_webhook_id("log-failed") is True
    assert await log_repo.exists_by_webhook_id("unknown") is False
