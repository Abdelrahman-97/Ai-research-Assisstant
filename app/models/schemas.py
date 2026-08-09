"""Pydantic schemas for the whole application.

Grouped by area:
  - Enums
  - Auth (users, sign up / sign in)
  - Payments (EasyKash)
  - Pipeline (data summary, proposed plan, approval, execution, run)

The pipeline mirrors the workflow stages:
    upload -> propose plan -> HUMAN CHECKPOINT -> write script -> execute
    -> verify -> write Results -> export .docx
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Language(str, Enum):
    python = "python"
    r = "r"


class TaskType(str, Enum):
    # Only one task is offered in v1, but the model is ready for more.
    results_section = "results_section"


class Scope(str, Enum):
    thesis = "thesis"
    studies = "studies"


class RunStatus(str, Enum):
    created = "created"                       # run exists, nothing uploaded yet
    uploaded = "uploaded"                     # data + protocol uploaded
    awaiting_payment = "awaiting_payment"     # price estimated, waiting to be paid
    paid = "paid"                             # payment confirmed; analysis unlocked
    awaiting_approval = "awaiting_approval"   # waiting for the human checkpoint
    approved = "approved"                     # plan approved (or edited + approved)
    script_ready = "script_ready"             # script generated (preview available)
    executing = "executing"
    executed = "executed"                     # artifacts collected
    writing = "writing"
    completed = "completed"                   # Results section + document(s) ready
    accepted = "accepted"                     # user accepted results; 30-day clock starts
    expired = "expired"                       # storage window elapsed; files purged
    failed = "failed"


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    task: TaskType = TaskType.results_section
    scope: Scope


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    task: TaskType
    scope: Scope
    has_paid: bool = False
    created_at: datetime = Field(default_factory=_now)


class User(UserPublic):
    """Internal user record — includes the password hash. Never returned to clients."""

    password_hash: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# --------------------------------------------------------------------------- #
# Payments (EasyKash)
# --------------------------------------------------------------------------- #
class PaymentLink(BaseModel):
    url: str
    reference: str = Field(..., description="Our reference id echoed back by the gateway")
    amount_egp: int


class PaymentCallback(BaseModel):
    """Shape of the success callback EasyKash posts to our webhook.

    Field names are mapped in services/payments.py; this is our normalized form.
    """

    reference: str
    status: str
    signature: str | None = None


# --------------------------------------------------------------------------- #
# Pricing
# --------------------------------------------------------------------------- #
class EstimateRequest(BaseModel):
    """User-supplied inputs for the price estimate (word count is user-chosen)."""

    word_count: int = Field(..., ge=100, le=20000, description="Target words for the Results section")


class PriceQuote(BaseModel):
    amount_egp: int
    currency: str = "EGP"
    # Transparent line items so the user sees how the price was built.
    breakdown: dict[str, int] = Field(default_factory=dict)
    estimated_tests: int = 0
    word_count: int = 0


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
class ColumnSummary(BaseModel):
    name: str
    dtype: str
    non_null: int
    n_unique: int
    sample_values: list[str] = Field(default_factory=list)


class DataSummary(BaseModel):
    n_rows: int
    n_cols: int
    columns: list[ColumnSummary] = Field(default_factory=list)


class IntegrityReport(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list)
    summary: DataSummary | None = None


class ProposedTest(BaseModel):
    """A statistical test the AI proposes, with citable reasoning."""

    name: str = Field(..., description="e.g. 'Independent samples t-test'")
    reasoning: str = Field(..., description="Why this test fits the data + protocol")
    variables: list[str] = Field(
        default_factory=list, description="Columns the test uses"
    )
    assumptions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class TestConfirmation(BaseModel):
    """Mandatory human checkpoint: confirm or override the proposed test."""

    confirmed: bool
    edited_plan: ProposedTest | None = Field(
        default=None,
        description="If the user edited the plan, the revised version.",
    )
    note: str | None = None


class Artifact(BaseModel):
    """A single output from the sandbox run (table, figure, or raw output)."""

    kind: str = Field(..., description="'table' | 'figure' | 'raw'")
    path: str
    caption: str | None = None


class ExecutionResult(BaseModel):
    status: RunStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    artifacts: list[Artifact] = Field(default_factory=list)


class Run(BaseModel):
    """The full state of one analysis job, moved through the pipeline."""

    id: str
    user_id: str
    task: TaskType
    scope: Scope
    status: RunStatus = RunStatus.created

    # inputs
    protocol_text: str | None = None
    data_path: str | None = None

    # pricing + payment (payment happens per-run, after the estimate)
    quote: PriceQuote | None = None
    paid: bool = False
    payment_reference: str | None = None

    # working state
    data_summary: DataSummary | None = None
    proposed_test: ProposedTest | None = None
    approved_test: ProposedTest | None = None
    language: Language | None = None
    script: str | None = None
    execution: ExecutionResult | None = None

    # outputs
    results_markdown: str | None = None
    docx_path: str | None = None
    pdf_path: str | None = None

    # lifecycle / retention
    accepted_at: datetime | None = None
    expires_at: datetime | None = None

    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
