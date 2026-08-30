"""Blob store — binary files kept in the shared database.

The web service and the background worker run as separate Render services that do
NOT share a disk, so any file one produces and the other needs (the uploaded
dataset, generated figures/tables, the Word/PDF outputs) travels through here.

Keeping blobs in Postgres also makes them durable across redeploys, which is what
the 30-day retention promise requires. At launch scale (datasets capped at a few
tens of MB) this is more than adequate; swapping to object storage later means
reimplementing only this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db import BlobRow, SessionLocal


def _new_id() -> str:
    return uuid.uuid4().hex


def put(run_id: str, kind: str, filename: str, content: bytes) -> str:
    """Store bytes and return the new blob id."""
    blob_id = _new_id()
    with SessionLocal() as s:
        s.add(
            BlobRow(
                id=blob_id,
                run_id=run_id,
                kind=kind,
                filename=filename,
                content=content,
                created_at=datetime.now(timezone.utc),
            )
        )
        s.commit()
    return blob_id


def get(blob_id: str) -> tuple[str, bytes] | None:
    """Return (filename, content) for a blob id, or None if it's gone."""
    with SessionLocal() as s:
        row = s.get(BlobRow, blob_id)
        if row is None:
            return None
        return row.filename, row.content


def list_for_run(run_id: str, kind: str | None = None) -> list[tuple[str, str, str]]:
    """Return [(blob_id, kind, filename)] for a run, optionally filtered by kind."""
    with SessionLocal() as s:
        q = s.query(BlobRow).filter(BlobRow.run_id == run_id)
        if kind is not None:
            q = q.filter(BlobRow.kind == kind)
        return [(r.id, r.kind, r.filename) for r in q.all()]


def delete_for_run(run_id: str) -> int:
    """Delete every blob belonging to a run (retention purge / account deletion)."""
    with SessionLocal() as s:
        rows = s.query(BlobRow).filter(BlobRow.run_id == run_id).all()
        n = len(rows)
        for row in rows:
            s.delete(row)
        s.commit()
        return n
