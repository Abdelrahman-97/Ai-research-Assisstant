"""30-day retention / cleanup tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.schemas import Artifact, ExecutionResult, Run, RunStatus, Scope, TaskType
from app.services import cleanup
from app.store import repository


def _make_accepted_run(tmp_path: Path, expires_in_days: int) -> Run:
    # Create real files that cleanup should delete.
    up_dir = tmp_path / "uploads"
    up_dir.mkdir(parents=True, exist_ok=True)
    data = up_dir / "data.csv"; data.write_text("group,score\na,1\n")
    docx = tmp_path / "r.docx"; docx.write_text("doc")
    pdf = tmp_path / "r.pdf"; pdf.write_text("pdf")
    art = tmp_path / "summary.csv"; art.write_text("t,p\n1,0.5\n")

    now = datetime.now(timezone.utc)
    run = Run(
        id=repository.new_id(), user_id="u1", task=TaskType.results_section, scope=Scope.thesis,
        status=RunStatus.accepted, data_path=str(data),
        docx_path=str(docx), pdf_path=str(pdf),
        execution=ExecutionResult(status=RunStatus.executed,
                                  artifacts=[Artifact(kind="table", path=str(art))]),
        accepted_at=now, expires_at=now + timedelta(days=expires_in_days),
    )
    return repository.runs.create(run)


def test_expired_run_is_purged(tmp_path):
    run = _make_accepted_run(tmp_path, expires_in_days=-1)  # already expired
    docx = Path(run.docx_path)
    assert docx.exists()

    purged = cleanup.purge_expired()
    assert purged >= 1

    refreshed = repository.runs.get(run.id)
    assert refreshed.status == RunStatus.expired
    assert refreshed.docx_path is None
    assert not docx.exists()  # file actually deleted


def test_active_run_is_not_purged(tmp_path):
    run = _make_accepted_run(tmp_path, expires_in_days=30)  # still within window
    cleanup.purge_expired()
    refreshed = repository.runs.get(run.id)
    assert refreshed.status == RunStatus.accepted
    assert Path(run.docx_path).exists()
