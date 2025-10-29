"""Middleware for Instagram webhook signature verification."""

import hashlib
import hmac
import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class WebhookVerificationMiddleware(BaseHTTPMiddleware):
    """
    Verify Instagram webhook signatures using HMAC-SHA256.

    Instagram sends X-Hub-Signature-256 header with format: sha256=<signature>
    We compute HMAC-SHA256 of request body with app_secret and compare.
    """

    def __init__(self, app, app_secret: str, verify_webhook_paths: list[str], development_mode: bool = False):
        """
        Initialize webhook verification middleware.

        Args:
            app: FastAPI app instance
            app_secret: Instagram app secret for HMAC verification
            verify_webhook_paths: List of paths that require verification (e.g., ["/webhook", "/webhook/"])
            development_mode: If True, skip verification for testing
        """
        super().__init__(app)
        self.app_secret = app_secret.encode()
        self.verify_webhook_paths = verify_webhook_paths
        self.development_mode = development_mode

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and verify webhook signature if needed.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response from next handler or 401 if verification fails
        """
        # Check if this path requires verification
        if not self._should_verify(request):
            return await call_next(request)

        # Skip verification in development mode
        if self.development_mode:
            logger.warning("Development mode: skipping webhook verification")
            return await call_next(request)

        # Only verify POST requests (webhooks)
        if request.method != "POST":
            return await call_next(request)

        # Get signature from header
        signature_header = request.headers.get("X-Hub-Signature-256")
        if not signature_header:
            # Try fallback to SHA1 (older Instagram webhooks)
            signature_header = request.headers.get("X-Hub-Signature")

            if not signature_header:
                logger.warning("Missing webhook signature header")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing signature header"},
                )

        # Read request body
        body = await request.body()

        # Verify signature
        if not self._verify_signature(signature_header, body):
            logger.warning(f"Invalid webhook signature from {request.client.host}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid signature"},
            )

        logger.debug("Webhook signature verified successfully")

        # Reconstruct request with body for downstream handlers
        # This is necessary because we've already read the body
        async def receive():
            return {"type": "http.request", "body": body}

        request._receive = receive

        return await call_next(request)

    def _should_verify(self, request: Request) -> bool:
        """
        Check if request path requires verification.

        Args:
            request: FastAPI request

        Returns:
            True if verification required, False otherwise
        """
        path = request.url.path
        return any(path.startswith(verify_path) for verify_path in self.verify_webhook_paths)

    def _verify_signature(self, signature_header: str, body: bytes) -> bool:
        """
        Verify HMAC signature.

        Args:
            signature_header: Signature from request header (e.g., "sha256=abc123...")
            body: Request body bytes

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Parse signature header format: "sha256=<hex>" or "sha1=<hex>"
            algorithm, provided_signature = signature_header.split("=", 1)

            # Compute expected signature based on algorithm
            if algorithm == "sha256":
                expected_signature = hmac.new(
                    self.app_secret,
                    body,
                    hashlib.sha256
                ).hexdigest()
            elif algorithm == "sha1":
                expected_signature = hmac.new(
                    self.app_secret,
                    body,
                    hashlib.sha1
                ).hexdigest()
            else:
                logger.warning(f"Unsupported signature algorithm: {algorithm}")
                return False

            # Use constant-time comparison to prevent timing attacks
            return hmac.compare_digest(expected_signature, provided_signature)

        except ValueError as e:
            logger.warning(f"Failed to parse signature header: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error verifying signature: {e}")
            return False
