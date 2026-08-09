"""In-memory data store.

This is a temporary stand-in for a real database. Every method here is what a
Postgres-backed repository would also expose, so swapping this out later means
reimplementing this one file (e.g. with SQLAlchemy) without touching callers.

NOT for production: data lives in process memory and is lost on restart, and it
is not safe across multiple worker processes.
"""

from __future__ import annotations

import threading
import uuid

from app.models.schemas import Run, User


def new_id() -> str:
    return uuid.uuid4().hex


class UserRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, User] = {}
        self._by_email: dict[str, str] = {}  # email -> id
        self._lock = threading.Lock()

    def create(self, user: User) -> User:
        with self._lock:
            if user.email in self._by_email:
                raise ValueError("A user with that email already exists.")
            self._by_id[user.id] = user
            self._by_email[user.email] = user.id
            return user

    def get(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        uid = self._by_email.get(email)
        return self._by_id.get(uid) if uid else None

    def save(self, user: User) -> User:
        with self._lock:
            self._by_id[user.id] = user
            return user


class RunRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Run] = {}
        self._lock = threading.Lock()

    def create(self, run: Run) -> Run:
        with self._lock:
            self._by_id[run.id] = run
            return run

    def get(self, run_id: str) -> Run | None:
        return self._by_id.get(run_id)

    def save(self, run: Run) -> Run:
        with self._lock:
            self._by_id[run.id] = run
            return run

    def list_for_user(self, user_id: str) -> list[Run]:
        return [r for r in self._by_id.values() if r.user_id == user_id]


# Module-level singletons used across the app. Replacing these with a DB-backed
# implementation is the only change needed to persist data.
users = UserRepository()
runs = RunRepository()
