"""Pydantic schemas modelling the pipeline.

These mirror the workflow stages:
    upload -> propose test -> HUMAN CHECKPOINT -> execute in sandbox
    -> retrieve artifacts -> write Results section -> export .docx
"""

from enum import Enum

from pydantic import BaseModel, Field


class Language(str, Enum):
    python = "python"
    r = "r"


class RunStatus(str, Enum):
    uploaded = "uploaded"
    test_proposed = "test_proposed"
    awaiting_confirmation = "awaiting_confirmation"
    confirmed = "confirmed"
    executing = "executing"
    executed = "executed"
    writing = "writing"
    completed = "completed"
    failed = "failed"


class ProposedTest(BaseModel):
    """A statistical test the AI proposes, with citable reasoning."""

    name: str = Field(..., description="e.g. 'Independent samples t-test'")
    reasoning: str = Field(..., description="Why this test fits the data + protocol")
    assumptions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class TestConfirmation(BaseModel):
    """Mandatory human checkpoint: confirm or override the proposed test."""

    confirmed: bool
    override_test_name: str | None = Field(
        default=None,
        description="If not confirmed, the test the user chose instead.",
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
    artifacts: list[Artifact] = Field(default_factory=list)
