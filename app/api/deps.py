"""Shared API dependencies (current user).

Payment is enforced per-run in the orchestrator (not per-user), because pricing
and payment happen after the free upload + estimate. So there is no user-level
paywall dependency here.
"""

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
    payload = decode_access_token(creds.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
    user = repository.users.get(payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found."
        )
    # Token version must match — a password reset bumps it, logging out old sessions.
    if int(payload.get("tv", 0)) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please log in again.",
        )
    return user
