"""Auth routes: sign up, sign in, email verification, password reset.

Sign-up captures the account's default scope and sends a verification email.
Password reset is token-based and, on success, bumps the user's token_version so
old sessions and the used reset link stop working.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.config import settings
from app.models.schemas import (
    EmailRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenRequest,
    TokenResponse,
    User,
    UserPublic,
)
from app.ratelimit import limiter
from app.services import email
from app.services.security import (
    create_access_token,
    create_email_token,
    decode_email_token,
    hash_password,
    verify_password,
)
from app.store import repository

router = APIRouter(prefix="/auth", tags=["auth"])


def _send_verification(user: User) -> None:
    token = create_email_token(user.id, "verify", user.token_version, settings.verify_token_minutes)
    link = f"{settings.frontend_url.rstrip('/')}/verify.html?token={token}"
    email.send_verification(user.email, link)


def _send_reset(user: User) -> None:
    token = create_email_token(user.id, "reset", user.token_version, settings.reset_token_minutes)
    link = f"{settings.frontend_url.rstrip('/')}/reset.html?token={token}"
    email.send_password_reset(user.email, link)


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def signup(request: Request, body: SignupRequest) -> TokenResponse:
    if repository.users.get_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )
    user = User(
        id=repository.new_id(),
        email=body.email,
        task=body.task,
        scope=body.scope,
        password_hash=hash_password(body.password),
    )
    repository.users.create(user)
    _send_verification(user)
    token = create_access_token(user.id, user.token_version)
    return TokenResponse(access_token=token, user=UserPublic(**user.model_dump()))


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest) -> TokenResponse:
    user = repository.users.get_by_email(body.email)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    token = create_access_token(user.id, user.token_version)
    return TokenResponse(access_token=token, user=UserPublic(**user.model_dump()))


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic(**user.model_dump())


@router.post("/verify-email", response_model=UserPublic)
def verify_email(body: TokenRequest) -> UserPublic:
    decoded = decode_email_token(body.token, "verify")
    if not decoded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link.",
        )
    user_id, _tv = decoded
    user = repository.users.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown user.")
    user.email_verified = True
    repository.users.save(user)
    return UserPublic(**user.model_dump())


@router.post("/resend-verification")
def resend_verification(body: EmailRequest) -> dict:
    user = repository.users.get_by_email(body.email)
    if user and not user.email_verified:
        _send_verification(user)
    # Generic response — don't reveal whether the email exists.
    return {"ok": True, "detail": "If that account exists and is unverified, a link was sent."}


@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(request: Request, body: ForgotPasswordRequest) -> dict:
    user = repository.users.get_by_email(body.email)
    if user:
        _send_reset(user)
    # Always generic — never leak whether the email is registered.
    return {"ok": True, "detail": "If that email is registered, a reset link was sent."}


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(body: ResetPasswordRequest) -> TokenResponse:
    decoded = decode_email_token(body.token, "reset")
    if not decoded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link.",
        )
    user_id, tv = decoded
    user = repository.users.get(user_id)
    if not user or tv != user.token_version:
        # Wrong user, or the link was already used (token_version moved on).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is no longer valid.",
        )
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # invalidate old sessions + this reset link
    repository.users.save(user)
    token = create_access_token(user.id, user.token_version)
    return TokenResponse(access_token=token, user=UserPublic(**user.model_dump()))
