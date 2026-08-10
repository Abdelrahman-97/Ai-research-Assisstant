"""Database engine + tables (SQLAlchemy).

Persistence is intentionally simple: each User/Run is stored as its JSON payload
in a single `data` column, with the columns we actually query on (id, email,
user_id) promoted to real indexed columns. This keeps the rich nested pydantic
models intact without a heavy ORM mapping, and makes swapping SQLite -> Postgres
a one-line change (DATABASE_URL).
"""

from __future__ import annotations

import os

from sqlalchemy import Column, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

# Env var wins over the settings default (used by tests to point at a temp DB).
DATABASE_URL = os.environ.get("DATABASE_URL", settings.database_url)

# Managed Postgres providers (Render, Heroku) hand out URLs starting with
# "postgres://", but SQLAlchemy needs an explicit driver. Normalize it.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

_connect_args: dict = {}
_engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    if ":memory:" in DATABASE_URL:
        # Keep one shared connection so in-memory data survives across sessions.
        _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(
    DATABASE_URL, connect_args=_connect_args, future=True, **_engine_kwargs
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, future=True
)
Base = declarative_base()


class UserRow(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    data = Column(Text, nullable=False)


class RunRow(Base):
    __tablename__ = "runs"
    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    data = Column(Text, nullable=False)


def init_db() -> None:
    """Create tables if they don't exist. Idempotent."""
    # Ensure the SQLite file's directory exists.
    if DATABASE_URL.startswith("sqlite:///") and ":memory:" not in DATABASE_URL:
        path = DATABASE_URL.replace("sqlite:///", "", 1)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    Base.metadata.create_all(engine)


# Create tables on import so any caller (including tests that don't trigger the
# app's startup event) has them available.
init_db()
