"""Pipeline routes — one endpoint per stage of a run.

Auth is required throughout (get_current_user). Upload and the price estimate are
FREE; everything from the plan onward requires the run to be paid (enforced in the
orchestrator). The human checkpoint is at /approve.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.config import settings
from app.models.schemas import (
    EstimateRequest,
    Language,
    PaymentLink,
    Run,
    TestConfirmation,
    User,
)
from app.services import cleanup, orchestrator, payments
from app.services.orchestrator import PipelineError
from app.store import repository

router = APIRouter(prefix="/runs", tags=["runs"])

_ALLOWED_SUFFIXES = {".xlsx", ".xls", ".csv", ".tsv"}


def _get_owned_run(run_id: str, user: User) -> Run:
    run = repository.runs.get(run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return run


def _guard(fn):
    """Translate orchestrator PipelineErrors into 409 responses."""
    try:
        return fn()
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("", response_model=Run, status_code=status.HTTP_201_CREATED)
def create_run(user: User = Depends(get_current_user)) -> Run:
    return orchestrator.create_run(user.id, user.task, user.scope)


@router.post("/{run_id}/upload", response_model=Run)
async def upload(
    run_id: str,
    protocol: str = Form(..., description="Protocol / methods text"),
    data_file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> Run:
    run = _get_owned_run(run_id, user)

    suffix = Path(data_file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(_ALLOWED_SUFFIXES)}",
        )

    dest_dir = Path(settings.data_dir) / "uploads" / run_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"data{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(data_file.file, f)

    return orchestrator.ingest(run, protocol_text=protocol, data_path=str(dest))


@router.post("/{run_id}/estimate", response_model=Run)
def estimate(
    run_id: str,
    body: EstimateRequest,
    user: User = Depends(get_current_user),
) -> Run:
    """Free: compute the price from scope, data, estimated tests, and word count."""
    run = _get_owned_run(run_id, user)
    return _guard(lambda: orchestrator.estimate(run, body.word_count))


@router.post("/{run_id}/pay-link", response_model=PaymentLink)
def pay_link(run_id: str, user: User = Depends(get_current_user)) -> PaymentLink:
    """Create the EasyKash payment link for this run's quoted price."""
    run = _get_owned_run(run_id, user)
    if run.quote is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Get a price estimate before requesting a payment link.",
        )
    return payments.create_payment_link(run.id, user.email, run.quote.amount_egp)


@router.post("/{run_id}/plan", response_model=Run)
def propose_plan(run_id: str, user: User = Depends(get_current_user)) -> Run:
    run = _get_owned_run(run_id, user)
    return _guard(lambda: orchestrator.propose_plan(run))


@router.post("/{run_id}/approve", response_model=Run)
def approve_plan(
    run_id: str,
    confirmation: TestConfirmation,
    user: User = Depends(get_current_user),
) -> Run:
    run = _get_owned_run(run_id, user)
    return _guard(lambda: orchestrator.approve_plan(run, confirmation))


@router.post("/{run_id}/script", response_model=Run)
def generate_script(
    run_id: str,
    language: Language = Language.python,
    user: User = Depends(get_current_user),
) -> Run:
    run = _get_owned_run(run_id, user)
    return _guard(lambda: orchestrator.generate_script(run, language))


@router.post("/{run_id}/execute", response_model=Run)
def execute(run_id: str, user: User = Depends(get_current_user)) -> Run:
    run = _get_owned_run(run_id, user)
    return _guard(lambda: orchestrator.run_script(run))


@router.post("/{run_id}/results", response_model=Run)
def write_results(run_id: str, user: User = Depends(get_current_user)) -> Run:
    run = _get_owned_run(run_id, user)
    return _guard(lambda: orchestrator.write_results(run))


@router.post("/{run_id}/accept", response_model=Run)
def accept(run_id: str, user: User = Depends(get_current_user)) -> Run:
    """User accepts the finished results — starts the 30-day retention window."""
    run = _get_owned_run(run_id, user)
    return _guard(lambda: orchestrator.accept(run))


@router.get("/{run_id}", response_model=Run)
def get_run(run_id: str, user: User = Depends(get_current_user)) -> Run:
    return _get_owned_run(run_id, user)


@router.get("/{run_id}/download")
def download(
    run_id: str,
    format: str = Query("word", pattern="^(word|pdf)$"),
    user: User = Depends(get_current_user),
):
    """Download the results as Word (default) or PDF."""
    run = _get_owned_run(run_id, user)
    if cleanup.is_expired(run):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This run's files have expired (30-day storage window elapsed).",
        )

    path = run.pdf_path if format == "pdf" else run.docx_path
    if not path or not Path(path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No results document yet — complete the run first.",
        )
    media = (
        "application/pdf"
        if format == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path, media_type=media, filename=f"results_{run_id}.{'pdf' if format=='pdf' else 'docx'}")
