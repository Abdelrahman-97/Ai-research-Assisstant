"""Data store — SQLAlchemy-backed.

Same interface the code has always used (`repository.users`, `repository.runs`,
`repository.new_id`), now persisted to a real database. Each record is stored as
its JSON payload with the queried columns promoted; see app/db.py.

Switching between SQLite and Postgres is just the DATABASE_URL setting — nothing
in this file changes.
"""

from __future__ import annotations

import uuid

from app.db import RunRow, SessionLocal, UserRow
from app.models.schemas import Run, User


def new_id() -> str:
    return uuid.uuid4().hex


class UserRepository:
    def create(self, user: User) -> User:
        with SessionLocal() as s:
            exists = s.query(UserRow).filter(UserRow.email == user.email).first()
            if exists:
                raise ValueError("A user with that email already exists.")
            s.add(UserRow(id=user.id, email=user.email, data=user.model_dump_json()))
            s.commit()
        return user

    def get(self, user_id: str) -> User | None:
        with SessionLocal() as s:
            row = s.get(UserRow, user_id)
            return User.model_validate_json(row.data) if row else None

    def get_by_email(self, email: str) -> User | None:
        with SessionLocal() as s:
            row = s.query(UserRow).filter(UserRow.email == email).first()
            return User.model_validate_json(row.data) if row else None

    def save(self, user: User) -> User:
        with SessionLocal() as s:
            row = s.get(UserRow, user.id)
            if row:
                row.email = user.email
                row.data = user.model_dump_json()
            else:
                s.add(UserRow(id=user.id, email=user.email, data=user.model_dump_json()))
            s.commit()
        return user


class RunRepository:
    def create(self, run: Run) -> Run:
        with SessionLocal() as s:
            s.add(RunRow(id=run.id, user_id=run.user_id, data=run.model_dump_json()))
            s.commit()
        return run

    def get(self, run_id: str) -> Run | None:
        with SessionLocal() as s:
            row = s.get(RunRow, run_id)
            return Run.model_validate_json(row.data) if row else None

    def save(self, run: Run) -> Run:
        with SessionLocal() as s:
            row = s.get(RunRow, run.id)
            if row:
                row.data = run.model_dump_json()
            else:
                s.add(RunRow(id=run.id, user_id=run.user_id, data=run.model_dump_json()))
            s.commit()
        return run

    def list_for_user(self, user_id: str) -> list[Run]:
        with SessionLocal() as s:
            rows = s.query(RunRow).filter(RunRow.user_id == user_id).all()
            return [Run.model_validate_json(r.data) for r in rows]

    def all(self) -> list[Run]:
        with SessionLocal() as s:
            return [Run.model_validate_json(r.data) for r in s.query(RunRow).all()]


# Module-level singletons used across the app.
users = UserRepository()
runs = RunRepository()
