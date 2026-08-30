"""Pipeline routes — one endpoint per stage of a run.

Auth is required throughout (get_current_user). Upload and the price estimate are
FREE; everything from the plan onward requires the run to be paid (enforced in the
orchestrator). The human checkpoint is at /approve.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status,
)
from fastapi.responses import FileResponse, Response

from app.api.deps import get_current_user
from app.config import settings
from app.ratelimit import limiter
from app.models.schemas import (
    AssistantRequest,
    AssistantResponse,
    CreateRunRequest,
    EstimateRequest,
    Language,
    PaymentLink,
    Run,
    TestConfirmation,
    User,
)
from app.services import assistant, cleanup, orchestrator, payments
from app.services.llm_client import LLMError
from app.services.orchestrator import PipelineError
from app.store import blobs, repository

router = APIRouter(prefix="/runs", tags=["runs"])

_ALLOWED_SUFFIXES = {".xlsx", ".xls", ".csv", ".tsv"}


def _get_owned_run(run_id: str, user: User) -> Run:
    run = repository.runs.get(run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return run


def _guard(fn):
    """Translate pipeline/LLM errors into clean HTTP responses."""
    try:
        return fn()
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LLMError as exc:
        # AI provider timed out / rate-limited / errored — retryable.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is temporarily unavailable. Please try again in a moment.",
        ) from exc


@router.post("", response_model=Run, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_run(
    request: Request,
    body: CreateRunRequest,
    user: User = Depends(get_current_user),
) -> Run:
    return orchestrator.create_run(user.id, body.task, body.scope)


@router.get("", response_model=list[Run])
def list_runs(user: User = Depends(get_current_user)) -> list[Run]:
    """List the current user's runs, newest first (for the dashboard)."""
    runs = repository.runs.list_for_user(user.id)
    return sorted(runs, key=lambda r: r.created_at, reverse=True)


@router.post("/{run_id}/upload", response_model=Run)
async def upload(
    run_id: str,
    protocol: str = Form(..., description="Protocol / methods text"),
    data_file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> Run:
    run = _get_owned_run(run_id, user)

    if len(protocol) > settings.max_protocol_chars:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Protocol too long (max {settings.max_protocol_chars} characters).",
        )

    suffix = Path(data_file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(_ALLOWED_SUFFIXES)}",
        )

    dest_dir = Path(settings.data_dir) / "uploads" / run_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"data{suffix}"

    # Stream to disk with a size cap, aborting (and cleaning up) if exceeded.
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0
    with dest.open("wb") as f:
        while chunk := await data_file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large (max {settings.max_upload_mb} MB).",
                )
            f.write(chunk)

    # Persist the dataset to the shared blob store so the background worker (a
    # separate service, no shared disk) can run the analysis against it, and so
    # the file survives redeploys for the retention window.
    run.data_blob_id = blobs.put(
        run_id, kind="upload", filename=dest.name, content=dest.read_bytes()
    )
    return orchestrator.ingest(run, protocol_text=protocol, data_path=str(dest))


@router.post("/{run_id}/estimate", response_model=Run)
@limiter.limit("20/minute")
def estimate(
    request: Request,
    run_id: str,
    body: EstimateRequest,
    user: User = Depends(get_current_user),
) -> Run:
    """Free: compute the price from scope, data, estimated tests, and word count."""
    run = _get_owned_run(run_id, user)
    return _guard(lambda: orchestrator.estimate(run, body.word_count, body.assistant_tier))


@router.post("/{run_id}/pay-link", response_model=PaymentLink)
def pay_link(run_id: str, user: User = Depends(get_current_user)) -> PaymentLink:
    """Create the EasyKash payment link. Bills the customer total (incl. fees)."""
    run = _get_owned_run(run_id, user)
    if run.quote is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Get a price estimate before requesting a payment link.",
        )
    amount = run.quote.customer_total_egp or run.quote.amount_egp
    return payments.create_payment_link(run.id, user.email, amount)


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
    # In production the API doesn't run scripts itself: it enqueues the run for the
    # isolated background worker (which runs the script AND writes the results).
    # In inline mode it runs synchronously — used by dev and the test suite.
    if settings.execution_mode == "worker":
        return _guard(lambda: orchestrator.enqueue_execution(run))
    return _guard(lambda: orchestrator.run_script(run))


@router.post("/{run_id}/results", response_model=Run)
def write_results(run_id: str, user: User = Depends(get_current_user)) -> Run:
    run = _get_owned_run(run_id, user)
    return _guard(lambda: orchestrator.write_results(run))


@router.post("/{run_id}/assistant", response_model=AssistantResponse)
@limiter.limit("30/minute")
def talk_to_assistant(
    request: Request,
    run_id: str,
    body: AssistantRequest,
    user: User = Depends(get_current_user),
) -> AssistantResponse:
    """Free-text analyst layer: interpret the message, act on the run, reply.

    Requires the run to be paid (the interaction allowance is part of the job).
    """
    run = _get_owned_run(run_id, user)
    if not run.paid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pay for the run before using the assistant.",
        )
    try:
        reply, action = assistant.respond(run, body.message)
    except assistant.AssistantError as exc:
        # Allowance exhausted / disabled — surface as a normal chat reply, not an error.
        return AssistantResponse(
            reply=str(exc), action=None, remaining=assistant.remaining(run), run=run
        )
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is temporarily unavailable. Please try again in a moment.",
        ) from exc
    return AssistantResponse(
        reply=reply, action=action, remaining=assistant.remaining(run), run=run
    )


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

    media = (
        "application/pdf"
        if format == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    filename = f"results_{run_id}.{'pdf' if format == 'pdf' else 'docx'}"

    # Prefer the durable blob store (works even when the worker built the file on
    # another service, and survives redeploys); fall back to the local disk path.
    blob_id = run.pdf_blob_id if format == "pdf" else run.docx_blob_id
    if blob_id:
        got = blobs.get(blob_id)
        if got:
            return Response(content=got[1], media_type=media, headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            })

    path = run.pdf_path if format == "pdf" else run.docx_path
    if not path or not Path(path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No results document yet — complete the run first.",
        )
    return FileResponse(path, media_type=media, filename=filename)
