"""Authentication endpoints using OAuth2 password flow."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from src.api_v1.schemas import Token
from src.core.config import get_settings
from src.core.dependencies import get_user_repository
from src.core.services.auth_service import authenticate_user
from src.core.repositories.user_repository import UserRepository
from src.core.services.security import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    repo: UserRepository = Depends(get_user_repository),
):
    settings = get_settings()
    user = await authenticate_user(form_data.username, form_data.password, repo)
    if not user:
        logger.warning("Authentication failed for user %s", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.jwt.expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email, "scopes": form_data.scopes},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")
