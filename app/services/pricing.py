"""Pricing service.

Computes the price a researcher pays, from four inputs:
  - scope        (thesis chapter vs. a paper's results section)
  - the data     (size: rows x cols)
  - the tests    (how many statistical tests the analysis needs)
  - the words    (target length of the Results section, chosen by the user)

The number of tests is estimated by the AI from the protocol + data summary,
with a deterministic fallback so estimation never hard-depends on the LLM.

All rates live in config (price_* settings) so pricing can be tuned without
touching this code. The quote returns a transparent line-item breakdown.
"""

from __future__ import annotations

import math

from app.config import settings
from app.models.schemas import DataSummary, PriceQuote, Scope
from app.services.llm_client import LLMClient, LLMError

_ESTIMATE_SYSTEM = (
    "You are a biostatistician estimating scope of work. Given a study protocol "
    "and a data summary, estimate how many distinct statistical tests the analysis "
    "will require. Reply with JSON only."
)

_ESTIMATE_PROMPT = """\
Estimate the number of distinct statistical tests needed for this study.
Return ONLY: {{"n_tests": <integer between 1 and 20>}}

Protocol:
---
{protocol}
---
Data summary:
---
{data_summary}
---
"""


def _heuristic_test_count(data_summary: DataSummary | None) -> int:
    """Fallback estimate when the AI isn't available.

    Roughly: one test per pair of analysable variables, clamped to [1, 8].
    """
    if not data_summary or not data_summary.columns:
        return 1
    analysable = sum(
        1 for c in data_summary.columns if c.non_null > 0 and c.n_unique > 1
    )
    return max(1, min(8, math.ceil(analysable / 2)))


def estimate_test_count(
    protocol: str,
    data_summary: DataSummary | None,
    *,
    client: LLMClient | None = None,
) -> int:
    """Estimate how many tests the analysis needs (AI, with heuristic fallback)."""
    fallback = _heuristic_test_count(data_summary)
    try:
        client = client or LLMClient()
        summary_text = (
            f"rows={data_summary.n_rows}, cols={data_summary.n_cols}"
            if data_summary
            else "(no summary)"
        )
        payload = client.chat_json(
            [
                {"role": "system", "content": _ESTIMATE_SYSTEM},
                {
                    "role": "user",
                    "content": _ESTIMATE_PROMPT.format(
                        protocol=protocol.strip()[:4000], data_summary=summary_text
                    ),
                },
            ]
        )
        n = int(payload.get("n_tests", fallback))
        return max(1, min(20, n))
    except (LLMError, Exception):  # noqa: BLE001 - any failure -> heuristic
        return fallback


def gross_up_for_fees(net_egp: int) -> int:
    """Amount to bill the customer so you net `net_egp` after EasyKash fees.

    EasyKash takes a percentage commission plus a flat buyer surcharge. To keep
    your target net, we divide by (1 - commission) and add the flat surcharge.

    NOTE: the exact way EasyKash applies the commission and surcharge should be
    confirmed against the merchant portal; the "pass fees to customer" toggle in
    the dashboard can also handle this automatically (then just send your net).
    """
    rate = settings.easykash_commission_rate
    flat = settings.easykash_flat_fee_egp
    return math.ceil(net_egp / (1 - rate)) + flat


def quote(
    *,
    scope: Scope,
    data_summary: DataSummary | None,
    n_tests: int,
    word_count: int,
) -> PriceQuote:
    """Build a price quote with a transparent breakdown."""
    base = (
        settings.price_base_thesis_egp
        if scope == Scope.thesis
        else settings.price_base_paper_egp
    )
    tests_cost = n_tests * settings.price_per_test_egp
    words_cost = math.ceil(word_count / 1000) * settings.price_per_1000_words_egp

    cells = (data_summary.n_rows * data_summary.n_cols) if data_summary else 0
    data_cost = math.ceil(cells / 1000) * settings.price_per_1000_cells_egp

    breakdown = {
        f"base ({scope.value})": base,
        f"tests (x{n_tests})": tests_cost,
        f"words ({word_count})": words_cost,
        f"data ({cells} cells)": data_cost,
    }
    total = base + tests_cost + words_cost + data_cost
    customer_total = (
        gross_up_for_fees(total) if settings.easykash_pass_fees_to_customer else total
    )
    return PriceQuote(
        amount_egp=total,
        customer_total_egp=customer_total,
        breakdown=breakdown,
        estimated_tests=n_tests,
        word_count=word_count,
    )
