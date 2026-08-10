"""Auth routes: sign up and sign in.

Sign-up captures the user's chosen task and scope (thesis vs studies), as per the
workflow. On success both endpoints return a JWT access token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.models.schemas import (
    LoginRequest,
    SignupRequest,
    TokenResponse,
    User,
    UserPublic,
)
from app.ratelimit import limiter
from app.services.security import create_access_token, hash_password, verify_password
from app.store import repository

router = APIRouter(prefix="/auth", tags=["auth"])


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
    token = create_access_token(user.id)
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
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=UserPublic(**user.model_dump()))


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic(**user.model_dump())
