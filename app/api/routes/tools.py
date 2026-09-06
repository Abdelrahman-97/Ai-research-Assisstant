"""Free public statistics tools: sample-size, diagnostic accuracy, meta-analysis.

These need no account and no data upload — they're self-contained calculators
(also a marketing funnel to the full service). Rate-limited to prevent abuse.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.ratelimit import limiter
from app.services import diagnostic, meta_analysis, sample_size

router = APIRouter(prefix="/tools", tags=["tools"])


class SampleSizeRequest(BaseModel):
    design: str = Field(..., description="two_means | two_proportions | anova | correlation")
    params: dict = Field(default_factory=dict)


class DiagnosticRequest(BaseModel):
    tp: int
    fp: int
    fn: int
    tn: int


class MetaStudy(BaseModel):
    name: str | None = None
    effect: float
    se: float | None = None
    variance: float | None = None
    group: str | None = None


class MetaRequest(BaseModel):
    studies: list[MetaStudy]
    model: str = "random"
    subgroups: bool = True


@router.post("/sample-size")
@limiter.limit("60/minute")
def sample_size_tool(request: Request, body: SampleSizeRequest) -> dict:
    try:
        return sample_size.calculate(body.design, body.params)
    except sample_size.SampleSizeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/diagnostic")
@limiter.limit("60/minute")
def diagnostic_tool(request: Request, body: DiagnosticRequest) -> dict:
    try:
        return diagnostic.accuracy_2x2(body.tp, body.fp, body.fn, body.tn)
    except diagnostic.DiagnosticError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/meta-analysis")
@limiter.limit("30/minute")
def meta_analysis_tool(request: Request, body: MetaRequest) -> dict:
    try:
        studies = [s.model_dump() for s in body.studies]
        return meta_analysis.analyze(studies, model=body.model, subgroups=body.subgroups)
    except meta_analysis.MetaAnalysisError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
