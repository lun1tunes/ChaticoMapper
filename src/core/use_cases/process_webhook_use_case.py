"""Main use case for processing Instagram webhooks."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.instagram_comment import InstagramComment
from src.core.models.worker_app import WorkerApp
from src.core.repositories.instagram_comment_repository import InstagramCommentRepository
from src.core.repositories.worker_app_repository import WorkerAppRepository
from src.core.services.redis_cache_service import RedisCacheService
from src.core.use_cases.forward_webhook_use_case import ForwardWebhookUseCase

logger = logging.getLogger(__name__)


class ProcessWebhookUseCase:
    """
    Main orchestrator for webhook processing.

    Workflow:
    1. Extract comment data from webhook payload
    2. Resolve account_id directly from webhook entry
    3. Find active worker app for owner
    4. Store comment in database
    5. Forward webhook to worker app
    6. Return processing result
    """

    def __init__(
        self,
        session: AsyncSession,
        forward_webhook_uc: ForwardWebhookUseCase,
        redis_cache: Optional[RedisCacheService] = None,
    ):
        self.session = session
        self.forward_webhook_uc = forward_webhook_uc
        self.redis_cache = redis_cache
        self.worker_app_repo = WorkerAppRepository(session)
        self.comment_repo = InstagramCommentRepository(session)

    async def execute(
        self,
        webhook_payload: dict,
        original_headers: dict[str, str] | None = None,
        raw_payload: bytes | None = None,
    ) -> dict:
        """
        Process Instagram webhook payload.

        Args:
            webhook_payload: Instagram webhook payload dict
            original_headers: Original webhook headers to propagate to worker apps

        Returns:
            dict with:
                - success (bool): Whether processing succeeded
                - comments_processed (int): Number of comments processed
                - comments_skipped (int): Number of comments skipped
                - errors (list): List of error messages
        """
        errors = []
        comments_processed = 0
        comments_skipped = 0

        # Extract all comments from webhook
        try:
            comments = self._extract_comments(webhook_payload)
            logger.info(f"Extracted {len(comments)} comment(s) from webhook")

        except Exception as e:
            logger.error(f"Failed to extract comments from webhook: {e}")
            return {
                "success": False,
                "comments_processed": 0,
                "comments_skipped": 0,
                "errors": [f"Failed to extract comments: {str(e)}"],
            }

        # Process each comment
        for comment_data in comments:
            try:
                result = await self._process_single_comment(
                    comment_data,
                    webhook_payload,
                    original_headers=original_headers,
                    raw_payload=raw_payload,
                )

                if result.get("success"):
                    comments_processed += 1
                else:
                    comments_skipped += 1
                    if error := result.get("error"):
                        errors.append(error)

            except Exception as e:
                logger.exception(f"Unexpected error processing comment: {e}")
                comments_skipped += 1
                errors.append(f"Unexpected error: {str(e)}")

        success = comments_processed > 0 or len(comments) == 0

        return {
            "success": success,
            "comments_processed": comments_processed,
            "comments_skipped": comments_skipped,
            "errors": errors if errors else None,
        }

    async def _process_single_comment(
        self,
        comment_data: dict,
        webhook_payload: dict,
        original_headers: dict[str, str] | None = None,
        raw_payload: bytes | None = None,
    ) -> dict:
        """
        Process a single comment from webhook.

        Args:
            comment_data: Extracted comment data
            webhook_payload: Full webhook payload for forwarding
            original_headers: Original webhook headers to reuse

        Returns:
            dict with success status and details
        """
        comment_id = comment_data.get("comment_id")
        media_id = comment_data.get("media_id")
        account_id = comment_data.get("account_id")

        # Check if comment already processed
        if await self.comment_repo.exists_by_comment_id(comment_id):
            logger.debug(f"Comment already exists: comment_id={comment_id}")
            return {
                "success": False,
                "reason": "duplicate",
                "comment_id": comment_id,
            }

        if not account_id:
            error = f"Missing account_id in webhook entry for comment_id={comment_id}"
            logger.error(error)
            return {
                "success": False,
                "error": error,
                "comment_id": comment_id,
            }

        # Get worker app (with caching)
        worker_app = await self._get_worker_app_cached(account_id)

        if not worker_app:
            error = f"No worker app found for account_id={account_id}"
            logger.warning(error)
            return {
                "success": False,
                "error": error,
                "comment_id": comment_id,
            }

        # Store comment in database
        try:
            await self._store_comment(comment_data)
            logger.debug(f"Stored comment: comment_id={comment_id}")

        except Exception as e:
            logger.error(f"Failed to store comment: {e}")
            # Don't fail the whole process if storage fails
            await self.session.rollback()

        # Forward webhook to worker app
        forward_result = await self.forward_webhook_uc.execute(
            worker_app=worker_app,
            webhook_payload=webhook_payload,
            account_id=account_id,
            original_headers=original_headers,
            raw_payload=raw_payload,
        )

        if forward_result.get("success"):
            logger.info(
                "Successfully processed comment_id=%s for account_id=%s (username=%s)",
                comment_id,
                account_id,
                worker_app.owner_instagram_username,
            )
            return {
                "success": True,
                "comment_id": comment_id,
                "account_id": account_id,
                "worker_app_username": worker_app.owner_instagram_username,
                "worker_app_base_url": worker_app.base_url,
                "worker_app_webhook_url": worker_app.webhook_url,
                "processing_time_ms": forward_result.get("processing_time_ms"),
            }
        else:
            error_detail = forward_result.get("error")
            logger.error(
                "Failed to forward webhook to %s (account_id=%s): %s",
                worker_app.owner_instagram_username,
                account_id,
                error_detail,
            )
            return {
                "success": False,
                "error": error_detail,
                "comment_id": comment_id,
            }

    async def _get_worker_app_cached(self, account_id: str) -> Optional[WorkerApp]:
        """Retrieve worker app configuration with optional Redis caching."""
        cached_id: Optional[str] = None

        if self.redis_cache:
            cached_data = await self.redis_cache.get_worker_app(account_id)
            if cached_data:
                logger.debug("Worker app cache HIT for account_id=%s", account_id)
                cached_id = cached_data.get("id")
                if cached_id:
                    try:
                        worker_app = await self.worker_app_repo.get_by_id(UUID(cached_id))
                        if worker_app:
                            return worker_app
                    except (ValueError, TypeError):
                        logger.warning(
                            "Invalid worker app id in cache for account_id=%s",
                            account_id,
                        )

        # Cache miss or invalid entry -> fetch from DB
        worker_app = await self.worker_app_repo.get_by_account_id(account_id)

        if worker_app and self.redis_cache:
            cache_payload = {
                "id": str(worker_app.id),
                "account_id": worker_app.account_id,
                "owner_instagram_username": worker_app.owner_instagram_username,
                "base_url": worker_app.base_url,
                "webhook_url": worker_app.webhook_url,
                "user_id": str(worker_app.user_id) if worker_app.user_id else None,
            }
            await self.redis_cache.set_worker_app(account_id, cache_payload)

        return worker_app

    async def _store_comment(self, comment_data: dict) -> None:
        """Store comment in database."""
        comment = InstagramComment(
            comment_id=comment_data["comment_id"],
            media_id=comment_data["media_id"],
            owner_id=comment_data["account_id"],
            user_id=comment_data["user_id"],
            username=comment_data["username"],
            text=comment_data["text"],
            parent_id=comment_data.get("parent_id"),
            timestamp=comment_data["timestamp"],
            raw_webhook_data=comment_data.get("raw_data", {}),
        )

        self.session.add(comment)
        await self.session.commit()

    def _extract_comments(self, webhook_payload: dict) -> list[dict]:
        """
        Extract comment data from Instagram webhook payload.

        Args:
            webhook_payload: Instagram webhook payload

        Returns:
            List of comment data dicts
        """
        comments = []

        for entry in webhook_payload.get("entry", []):
            account_id = entry.get("id")
            entry_timestamp = entry.get("time", 0)

            for change in entry.get("changes", []):
                if change.get("field") != "comments":
                    continue

                value = change.get("value", {})

                # Extract comment info
                comment_id = value.get("id")
                media_id = value.get("media", {}).get("id")
                from_user = value.get("from", {})
                user_id = from_user.get("id")
                username = from_user.get("username")
                text = value.get("text", "")
                parent_id = value.get("parent_id")

                if not all([comment_id, account_id, user_id, username]):
                    logger.warning(f"Incomplete comment data, skipping: {value}")
                    continue

                if user_id == account_id:
                    logger.debug(
                        "Skipping comment from account owner | comment_id=%s account_id=%s",
                        comment_id,
                        account_id,
                    )
                    continue

                comments.append({
                    "comment_id": comment_id,
                    "media_id": media_id,
                    "account_id": account_id,
                    "user_id": user_id,
                    "username": username,
                    "text": text,
                    "parent_id": parent_id,
                    "timestamp": entry_timestamp,
                    "raw_data": value,
                })

        return comments
