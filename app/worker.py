"""Background execution worker.

Runs as its own Render service (see render.yaml). It is the ONLY place generated
scripts actually execute, which keeps arbitrary computation off the public API and
lets the API stay responsive.

Loop:
  1. Poll the shared database for runs in status `queued`.
  2. For each: materialize the uploaded dataset from the blob store to a temp
     file, run the previewed script in the sandbox, and — on success — write the
     Results section and store the Word/PDF outputs as blobs.
  3. The orchestrator marks the run `completed` or `failed`; the API polls it.

The worker (and only the worker) enables the subprocess execution path, because
Render's runtime has no Docker. That path runs with a stripped environment and
resource caps (see app/sandbox/docker_runner.py). For stronger isolation, point
the worker at a Docker-capable host and leave the fallback off.

Run it with:
    python -m app.worker
"""

from __future__ import annotations

import logging
import signal
import tempfile
import time
from pathlib import Path

from app.config import settings
from app.models.schemas import Run, RunStatus
from app.services import orchestrator
from app.store import blobs, repository

log = logging.getLogger("app.worker")

_STOP = False


def _claim_queued(limit: int) -> list[Run]:
    """Return up to `limit` runs waiting to execute, oldest first."""
    queued = [r for r in repository.runs.all() if r.status == RunStatus.queued]
    queued.sort(key=lambda r: r.created_at)
    return queued[:limit]


def _materialize_data(run: Run, workdir: Path) -> str | None:
    """Write the run's uploaded dataset from the blob store to `workdir`.

    Returns the local path, or None if the dataset can't be found.
    """
    if not run.data_blob_id:
        return None
    got = blobs.get(run.data_blob_id)
    if not got:
        return None
    filename, content = got
    dest = workdir / filename
    dest.write_bytes(content)
    return str(dest)


def process_run(run: Run) -> Run:
    """Execute one queued run end-to-end (script -> results). Testable in isolation."""
    log.info("Processing run %s (%s)", run.id, run.approved_test.name if run.approved_test else "?")
    with tempfile.TemporaryDirectory(prefix="ra_worker_") as tmp:
        data_path = _materialize_data(run, Path(tmp))
        if data_path is None:
            run.status = RunStatus.failed
            run.error = "Uploaded dataset is no longer available."
            return repository.runs.save(run)

        # Point the run at the freshly materialized file for this execution.
        run.data_path = data_path
        repository.runs.save(run)

        run = orchestrator.run_script(run)
        if run.status != RunStatus.executed:
            return run  # orchestrator already set `failed` + error

        return orchestrator.write_results(run)


def run_once() -> int:
    """One polling pass. Returns the number of runs processed."""
    claimed = _claim_queued(settings.worker_batch)
    for run in claimed:
        try:
            process_run(run)
        except Exception as exc:  # never let one bad run kill the loop
            log.exception("Run %s failed in worker", run.id)
            fresh = repository.runs.get(run.id) or run
            fresh.status = RunStatus.failed
            fresh.error = f"Worker error: {exc}"
            repository.runs.save(fresh)
    return len(claimed)


def _handle_signal(signum, _frame) -> None:  # pragma: no cover
    global _STOP
    _STOP = True
    log.info("Received signal %s — finishing current pass then exiting.", signum)


def run_forever() -> None:  # pragma: no cover - long-running loop
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log.info(
        "Worker started (poll=%.1fs, batch=%d, subprocess_fallback=%s).",
        settings.worker_poll_seconds, settings.worker_batch,
        settings.sandbox_allow_subprocess_fallback,
    )
    while not _STOP:
        try:
            did = run_once()
        except Exception:
            log.exception("Worker pass crashed; continuing.")
            did = 0
        if not did:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_forever()
