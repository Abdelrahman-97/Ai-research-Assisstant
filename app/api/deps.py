"""Shared API dependencies (current user, paid-access guard)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.schemas import User
from app.services.security import decode_access_token
from app.store import repository

_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> User:
    user_id = decode_access_token(creds.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
    user = repository.users.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found."
        )
    return user


def require_paid(user: User = Depends(get_current_user)) -> User:
    """Guard the pipeline behind a completed payment."""
    if not user.has_paid:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment required before using the assistant.",
        )
    return user
