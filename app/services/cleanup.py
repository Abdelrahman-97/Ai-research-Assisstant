"""Retention cleanup.

Inputs and outputs are kept for a limited window (settings.retention_days, 30 by
default) after the user ACCEPTS the results. Once the window elapses, this purges
the uploaded data, generated artifacts, and output documents, and marks the run
`expired` (the run record itself is kept as a lightweight receipt).

Run it on a schedule (e.g. daily cron):
    python -m app.services.cleanup
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.models.schemas import Run, RunStatus
from app.store import blobs, repository

log = logging.getLogger("app.cleanup")


def _delete_run_files(run: Run) -> None:
    """Remove this run's inputs and outputs, on disk and in the blob store."""
    # Durable copies in the shared blob store (uploads, artifacts, docx, pdf).
    blobs.delete_for_run(run.id)

    # Uploaded data lives in data/uploads/<run_id>/
    upload_dir = Path(settings.data_dir) / "uploads" / run.id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)

    for p in (run.docx_path, run.pdf_path):
        if p and Path(p).exists():
            try:
                Path(p).unlink()
            except OSError:
                pass

    if run.execution:
        for art in run.execution.artifacts:
            ap = Path(art.path)
            if ap.exists():
                try:
                    ap.unlink()
                except OSError:
                    pass


def is_expired(run: Run, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return (
        run.status == RunStatus.accepted
        and run.expires_at is not None
        and run.expires_at <= now
    )


def purge_expired(now: datetime | None = None) -> int:
    """Purge files for every run whose retention window has elapsed.

    Returns the number of runs purged.
    """
    now = now or datetime.now(timezone.utc)
    purged = 0
    for run in repository.runs.all():
        if not is_expired(run, now):
            continue
        _delete_run_files(run)
        run.status = RunStatus.expired
        run.data_path = None
        run.docx_path = None
        run.pdf_path = None
        run.data_blob_id = None
        run.docx_blob_id = None
        run.pdf_blob_id = None
        if run.execution:
            run.execution.artifacts = []
        run.updated_at = now
        repository.runs.save(run)
        purged += 1
    if purged:
        log.info("Purged %d expired run(s).", purged)
    return purged


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = purge_expired()
    print(f"Purged {count} expired run(s).")
