"""Security helpers: password hashing and signed tokens.

Passwords are hashed with bcrypt — we never store plaintext. We call the `bcrypt`
library directly rather than through passlib: passlib is unmaintained and its
bcrypt backend crashes to initialize against modern bcrypt (4.x) / Python 3.13+.

bcrypt only considers the first 72 bytes of a password and newer versions raise
on longer input, so we truncate to 72 bytes before hashing and verifying (doing
it in both places keeps them consistent).

Two kinds of JWT are issued:
  - access tokens: carry the user id (`sub`) and a token version (`tv`). Bumping
    the user's token_version invalidates all previously issued access tokens.
  - email tokens: single-purpose (`purpose` = "verify" | "reset"), short-lived,
    also carrying `tv` so a used reset link stops working after the reset.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


def _pw_bytes(password: str) -> bytes:
    # bcrypt uses at most the first 72 bytes; encode then truncate to stay within it.
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _encode(payload: dict, minutes: int) -> str:
    payload = {**payload, "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None


# --- Access tokens ------------------------------------------------------- #
def create_access_token(user_id: str, token_version: int = 0) -> str:
    return _encode({"sub": user_id, "tv": token_version}, settings.jwt_expire_minutes)


def decode_access_token(token: str) -> dict | None:
    """Return the token payload ({sub, tv, exp}) or None if invalid/expired."""
    payload = _decode(token)
    if not payload or "sub" not in payload:
        return None
    return payload


# --- Email tokens (verify / reset) --------------------------------------- #
def create_email_token(user_id: str, purpose: str, token_version: int, minutes: int) -> str:
    return _encode({"sub": user_id, "purpose": purpose, "tv": token_version}, minutes)


def decode_email_token(token: str, purpose: str) -> tuple[str, int] | None:
    """Return (user_id, token_version) if the token is valid for `purpose`, else None."""
    payload = _decode(token)
    if not payload or payload.get("purpose") != purpose or "sub" not in payload:
        return None
    return payload["sub"], int(payload.get("tv", 0))
