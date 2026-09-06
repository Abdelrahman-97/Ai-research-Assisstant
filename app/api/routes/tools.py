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


class MetaRequest(BaseModel):
    # Studies are free-form dicts so each effect measure can carry its own fields
    # (effect/se, or n1/m1/sd1/..., or e1/n1/e2/n2, or r/n, or events/total),
    # plus optional group, moderator, and year.
    studies: list[dict]
    measure: str = "generic"       # generic|md|smd|or|rr|rd|peto|fisher_z|proportion|hr
    model: str = "random"          # random|fixed
    tau2_method: str = "DL"        # DL|PM|REML
    hksj: bool = False             # Hartung-Knapp CI
    subgroups: bool = True
    meta_regression: bool = True
    cumulative: bool = True
    bias_tests: bool = True


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
        return meta_analysis.analyze(
            body.studies, measure=body.measure, model=body.model,
            tau2_method=body.tau2_method, hksj=body.hksj, subgroups=body.subgroups,
            meta_regression=body.meta_regression, cumulative=body.cumulative,
            bias_tests=body.bias_tests,
        )
    except meta_analysis.MetaAnalysisError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
