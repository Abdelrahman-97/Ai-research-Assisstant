"""Output formatting: resolve a FormatSpec into concrete style parameters, and
provide the mock content used for the instant style-sample preview.

A FormatSpec picks a preset (or custom knobs, or an uploaded template). This
module turns any spec into a single ResolvedFormat that the report writer reads,
so all the "what does APA look like" knowledge lives in one place and is easy to
tune. Exact matching of a specific document is handled separately by the writer
(it opens the uploaded template and reuses its own styles).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import FormatSpec

# Built-in presets. Each is a plain look; "vancouver" is a generic numbered
# manuscript style (its many journal variants are covered by "match my
# document"). Values are the defaults a user can still override via custom knobs.
_PRESETS: dict[str, dict] = {
    "standard": {
        "label": "Standard academic",
        "font_name": "Times New Roman", "font_size_pt": 12.0,
        "line_spacing": 1.5, "heading_numbering": True, "columns": 1,
        "caption_above_table": True,
    },
    "apa": {
        "label": "APA 7th",
        "font_name": "Times New Roman", "font_size_pt": 12.0,
        "line_spacing": 2.0, "heading_numbering": False, "columns": 1,
        "caption_above_table": True,
    },
    "vancouver": {
        "label": "Vancouver (numbered)",
        "font_name": "Times New Roman", "font_size_pt": 12.0,
        "line_spacing": 1.5, "heading_numbering": True, "columns": 1,
        "caption_above_table": True,
    },
    "two_column": {
        "label": "Two-column manuscript",
        "font_name": "Times New Roman", "font_size_pt": 10.0,
        "line_spacing": 1.0, "heading_numbering": False, "columns": 2,
        "caption_above_table": True,
    },
    "custom": {
        "label": "Custom",
        "font_name": "Times New Roman", "font_size_pt": 12.0,
        "line_spacing": 1.5, "heading_numbering": True, "columns": 1,
        "caption_above_table": True,
    },
    "template": {
        "label": "Match my document",
        # Inherited from the uploaded template; these are only fallbacks used if a
        # style is missing there.
        "font_name": "Times New Roman", "font_size_pt": 12.0,
        "line_spacing": 1.5, "heading_numbering": True, "columns": 1,
        "caption_above_table": True,
    },
}

# What the frontend shows as choosable presets (order matters).
PRESET_ORDER = ["standard", "apa", "vancouver", "two_column", "template", "custom"]


@dataclass
class ResolvedFormat:
    preset: str
    font_name: str
    font_size_pt: float
    line_spacing: float
    heading_numbering: bool
    columns: int
    caption_above_table: bool
    figure_start_number: int
    table_start_number: int
    use_template: bool
    template_blob_id: str | None


def resolve(spec: FormatSpec | None) -> ResolvedFormat:
    """Turn a (possibly partial) FormatSpec into concrete style parameters."""
    spec = spec or FormatSpec()
    base = _PRESETS.get(spec.preset, _PRESETS["standard"])
    return ResolvedFormat(
        preset=spec.preset if spec.preset in _PRESETS else "standard",
        font_name=spec.font_name or base["font_name"],
        font_size_pt=float(spec.font_size_pt or base["font_size_pt"]),
        line_spacing=float(spec.line_spacing or base["line_spacing"]),
        heading_numbering=(
            base["heading_numbering"] if spec.heading_numbering is None
            else bool(spec.heading_numbering)
        ),
        columns=int(base["columns"]),
        caption_above_table=(
            base["caption_above_table"] if spec.caption_above_table is None
            else bool(spec.caption_above_table)
        ),
        figure_start_number=int(spec.figure_start_number or 1),
        table_start_number=int(spec.table_start_number or 1),
        use_template=(spec.preset == "template" and bool(spec.template_blob_id)),
        template_blob_id=spec.template_blob_id,
    )


def presets_public() -> list[dict]:
    """Preset list for the frontend picker: name + human label."""
    return [{"name": p, "label": _PRESETS[p]["label"]} for p in PRESET_ORDER]


# --------------------------------------------------------------------------- #
# Mock content for the instant style sample (before any real analysis).
# A realistic one-pager: heading, a stats paragraph, a table, and a figure.
# --------------------------------------------------------------------------- #
SAMPLE_MARKDOWN = """\
# Results

## Baseline characteristics

A total of 60 participants were analysed, evenly split between the intervention
group (n = 30) and the control group (n = 30). The two groups were comparable at
baseline with respect to age and sex (p > 0.05).

## Primary outcome

The intervention group showed a significantly greater improvement in pain score
than the control group. Mean pain reduction was 3.8 (SD 1.2) in the intervention
group versus 2.1 (SD 1.4) in the control group, an independent-samples t-test
confirming the difference was statistically significant, **t(58) = 4.91,
p < 0.001**, with a large effect size (Cohen's d = 1.27).
"""

# A small table rendered as (headers, rows) — the writer draws it as a real table.
SAMPLE_TABLE_HEADERS = ["Group", "n", "Mean", "SD", "p-value"]
SAMPLE_TABLE_ROWS = [
    ["Intervention", "30", "3.8", "1.2", "<0.001"],
    ["Control", "30", "2.1", "1.4", ""],
]
SAMPLE_TABLE_CAPTION = "Pain reduction by group."
SAMPLE_FIGURE_CAPTION = "Mean pain reduction by group with 95% confidence intervals."
