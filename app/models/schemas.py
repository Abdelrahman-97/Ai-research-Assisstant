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
    results_section = "results_section"   # the AI results-section pipeline
    meta_analysis = "meta_analysis"       # comprehensive meta-analysis (paid tool)
    sample_size = "sample_size"           # sample-size / power (paid tool)
    diagnostic = "diagnostic"             # diagnostic accuracy from a 2x2 (paid tool)


# Task types that are deterministic "tool" jobs (structured inputs → computed
# report), as opposed to the AI results-section pipeline.
TOOL_TASKS = {TaskType.meta_analysis, TaskType.sample_size, TaskType.diagnostic}


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
    queued = "queued"                         # handed to the background worker
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
    name: str | None = Field(default=None, max_length=120)
    # Task + scope are now chosen per-job (at run creation), so they are optional
    # here and only act as the account's default.
    task: TaskType = TaskType.results_section
    scope: Scope = Scope.studies


class CreateRunRequest(BaseModel):
    """Task + scope are chosen when starting each job.

    Scope only matters for the results-section pipeline; the tool jobs
    (meta-analysis, sample-size, diagnostic) ignore it, so it defaults.
    """

    task: TaskType = TaskType.results_section
    scope: Scope = Scope.studies


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class TokenRequest(BaseModel):
    token: str


class EmailRequest(BaseModel):
    email: EmailStr


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str | None = None
    task: TaskType
    scope: Scope
    has_paid: bool = False
    email_verified: bool = False
    created_at: datetime = Field(default_factory=_now)


class User(UserPublic):
    """Internal user record — includes the password hash. Never returned to clients."""

    password_hash: str
    # Bumped on password reset to invalidate old sessions and used reset links.
    token_version: int = 0


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
    assistant_tier: str = Field(
        default="basic",
        description="Interaction tier: how many assistant messages are included.",
    )
    consultation: str = Field(
        default="none",
        description="Expert add-on: none | review (+fee) | full (expert does it all).",
    )


class FormatSpec(BaseModel):
    """How the final Results document should be styled.

    `preset` picks a built-in look; `custom` uses the knobs below; `template`
    matches an uploaded document's own styles (font, headings, captions).
    Any knob left None falls back to the preset's default, so custom overrides
    can be layered on top of a preset too.
    """

    preset: str = "standard"     # standard|apa|vancouver|two_column|custom|template
    font_name: str | None = None         # e.g. "Times New Roman", "Arial"
    font_size_pt: float | None = None    # e.g. 12
    line_spacing: float | None = None    # 1.0 | 1.5 | 2.0
    heading_numbering: bool | None = None  # numbered (1, 1.1) vs plain headings
    # Figures and tables are captioned "Figure N." / "Table N.". The chapter may
    # follow existing ones, so the first number is configurable.
    figure_start_number: int = 1
    table_start_number: int = 1
    caption_above_table: bool = True     # journals differ: table captions usually above
    template_blob_id: str | None = None  # uploaded style template (preset="template")


class PriceQuote(BaseModel):
    amount_egp: int                      # what you net (your price)
    customer_total_egp: int = 0          # what the customer is billed (incl. gateway fees)
    currency: str = "EGP"
    # Transparent line items so the user sees how the price was built.
    breakdown: dict[str, int] = Field(default_factory=dict)
    estimated_tests: int = 0
    word_count: int = 0
    assistant_tier: str = "basic"        # chosen interaction tier
    assistant_allowance: int = 0         # assistant messages included by that tier
    consultation: str = "none"           # expert add-on: none | review | full


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


class TestEvidence(BaseModel):
    """Reliable, curated methodological evidence for a statistical test.

    Sourced from a fixed in-app reference base (NOT the LLM), so the citation is
    always real and verifiable — never hallucinated.
    """

    matched: bool = False                      # True if found in the curated base
    canonical_name: str | None = None          # normalized test name we matched
    family: str | None = None                  # "parametric" | "non-parametric" | other
    when_to_use: str | None = None             # one-line rationale for this design
    assumptions: list[str] = Field(default_factory=list)
    citation: str | None = None                # canonical reference (e.g. Student, 1908)
    note: str | None = None                    # e.g. "no curated reference — verify manually"


class ProposedTest(BaseModel):
    """A statistical test the AI proposes, with citable reasoning."""

    name: str = Field(..., description="e.g. 'Independent samples t-test'")
    reasoning: str = Field(..., description="Why this test fits the data + protocol")
    variables: list[str] = Field(
        default_factory=list, description="Columns the test uses"
    )
    assumptions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    evidence: TestEvidence | None = None       # attached from the curated base


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


# --------------------------------------------------------------------------- #
# Analyst assistant (free-text control layer over the pipeline)
# --------------------------------------------------------------------------- #
class Analysis(BaseModel):
    """One statistical analysis within a run (a test + its script + its output).

    A run always has a primary analysis (the fields on Run itself). The assistant
    can add extra analyses here so one job can cover several tests.
    """

    test: ProposedTest
    language: Language = Language.python
    script: str | None = None
    execution: ExecutionResult | None = None


class AssistantAction(BaseModel):
    """A structured operation the analyst layer maps a free-text request to.

    The model may only emit these whitelisted types; the backend validates each
    against the run's state before applying it. `type == "none"` is a pure reply
    (explanation / clarification) with no side effect.
    """

    type: str = "none"          # none|explain|set_test|edit_variables|set_word_count|
                                # regenerate_script|run_analysis|write_results|
                                # filter_data|add_test
    params: dict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: str                    # "user" | "assistant"
    content: str
    action: AssistantAction | None = None
    created_at: datetime = Field(default_factory=_now)


class AssistantRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class AssistantResponse(BaseModel):
    reply: str
    action: AssistantAction | None = None
    remaining: int = 0           # assistant messages left in the allowance
    run: "Run"


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
    data_blob_id: str | None = None           # uploaded dataset in shared blob store

    # pricing + payment (payment happens per-run, after the estimate)
    quote: PriceQuote | None = None
    paid: bool = False
    payment_reference: str | None = None
    refunded: bool = False

    # working state
    data_summary: DataSummary | None = None
    proposed_test: ProposedTest | None = None
    approved_test: ProposedTest | None = None
    language: Language | None = None
    script: str | None = None
    execution: ExecutionResult | None = None

    # extra analyses added via the assistant (the primary test stays in the
    # fields above; these are additional tests so one run can cover several)
    additional_analyses: list[Analysis] = Field(default_factory=list)

    # analyst conversation + interaction allowance
    messages: list[ChatMessage] = Field(default_factory=list)
    assistant_tier: str = "basic"
    assistant_allowance: int = 0
    assistant_used: int = 0

    # expert add-on chosen at the estimate step (none | review | full)
    consultation: str = "none"

    # output formatting (how the .docx/.pdf are styled)
    format_spec: FormatSpec | None = None
    # language of the generated Results prose: "en" | "ar"
    output_language: str = "en"

    # tool jobs (meta-analysis / sample-size / diagnostic): structured inputs the
    # user supplied and the computed result (rendered into the report).
    tool_inputs: dict | None = None
    tool_result: dict | None = None

    # outputs
    results_markdown: str | None = None
    docx_path: str | None = None
    pdf_path: str | None = None
    docx_blob_id: str | None = None           # generated Word doc in shared blob store
    pdf_blob_id: str | None = None            # generated PDF in shared blob store

    # lifecycle / retention
    accepted_at: datetime | None = None
    expires_at: datetime | None = None

    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# Resolve the forward reference in AssistantResponse now that Run is defined.
AssistantResponse.model_rebuild()
