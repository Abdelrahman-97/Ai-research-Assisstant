"""Meta-analysis data ingestion.

Turns an uploaded study-level spreadsheet (Excel or CSV) into the list of study
dicts the meta-analysis engine expects, with forgiving header matching and clear,
per-row validation so the researcher can fix problems *before* paying.

The columns required depend on the chosen effect measure (2x2 counts for OR/RR,
means+SDs for MD/SMD, effect+SE for generic/HR, r+n for correlations, etc.).
Optional trailing columns — group (subgroups), moderator (meta-regression) and
year (cumulative) — are picked up automatically when present.
"""

from __future__ import annotations

import math
from pathlib import Path

from app.services.integrity_checker import read_dataframe
from app.services import meta_analysis

# --------------------------------------------------------------------------- #
# Per-measure column schema. Each entry: (key, canonical_header, human_label).
# `key` is what the engine reads; `canonical_header` is what our template writes;
# aliases (below) let us accept many header spellings on upload.
# --------------------------------------------------------------------------- #
MEASURE_COLUMNS: dict[str, list[tuple[str, str, str]]] = {
    "generic":    [("name", "name", "Study"), ("effect", "effect", "Effect size"),
                   ("se", "standard_error", "Standard error")],
    "hr":         [("name", "name", "Study"), ("effect", "logHR", "log Hazard ratio"),
                   ("se", "standard_error", "Standard error")],
    "or":         [("name", "name", "Study"), ("e1", "events1", "Events (group 1)"),
                   ("n1", "n1", "N (group 1)"), ("e2", "events2", "Events (group 2)"),
                   ("n2", "n2", "N (group 2)")],
    "md":         [("name", "name", "Study"), ("n1", "n1", "N (group 1)"),
                   ("m1", "mean1", "Mean (group 1)"), ("sd1", "sd1", "SD (group 1)"),
                   ("n2", "n2", "N (group 2)"), ("m2", "mean2", "Mean (group 2)"),
                   ("sd2", "sd2", "SD (group 2)")],
    "fisher_z":   [("name", "name", "Study"), ("r", "r", "Correlation r"),
                   ("n", "n", "Sample size")],
    "proportion": [("name", "name", "Study"), ("events", "events", "Events"),
                   ("total", "total", "Total")],
}
# OR / RR / RD / Peto share the 2x2 layout; MD / SMD share the means layout.
MEASURE_COLUMNS["rr"] = MEASURE_COLUMNS["rd"] = MEASURE_COLUMNS["peto"] = MEASURE_COLUMNS["or"]
MEASURE_COLUMNS["smd"] = MEASURE_COLUMNS["md"]

# Optional trailing columns (added by the researcher only if they need them).
OPTIONAL_COLUMNS: list[tuple[str, str, str]] = [
    ("group", "group", "Subgroup"),
    ("moderator", "moderator", "Moderator (number)"),
    ("year", "year", "Year"),
]

# Header aliases -> canonical key. Matching is case-insensitive and ignores
# spaces, underscores, hyphens and dots (see _norm).
_ALIASES: dict[str, str] = {
    "name": "name", "study": "name", "studyname": "name", "author": "name",
    "authoryear": "name", "label": "name", "trial": "name", "reference": "name",
    "effect": "effect", "es": "effect", "yi": "effect", "effectsize": "effect",
    "estimate": "effect", "loghr": "effect", "logor": "effect", "logrr": "effect",
    "se": "se", "stderr": "se", "standarderror": "se", "sei": "se", "seyi": "se",
    "variance": "variance", "var": "variance", "vi": "variance",
    "e1": "e1", "events1": "e1", "eventst": "e1", "eventstreatment": "e1",
    "eventsintervention": "e1", "ei": "e1", "cases1": "e1",
    "n1": "n1", "total1": "n1", "nt": "n1", "ntreatment": "n1",
    "nintervention": "n1", "ni": "n1",
    "e2": "e2", "events2": "e2", "eventsc": "e2", "eventscontrol": "e2",
    "ec": "e2", "cases2": "e2",
    "n2": "n2", "total2": "n2", "nc": "n2", "ncontrol": "n2",
    "m1": "m1", "mean1": "m1", "meant": "m1", "meanintervention": "m1", "mi": "m1",
    "sd1": "sd1", "std1": "sd1", "sdt": "sd1", "stdev1": "sd1",
    "m2": "m2", "mean2": "m2", "meanc": "m2", "meancontrol": "m2",
    "sd2": "sd2", "std2": "sd2", "sdc": "sd2", "stdev2": "sd2",
    "r": "r", "correlation": "r", "corr": "r", "rho": "r", "pearsonr": "r",
    "n": "n", "total": "total", "samplesize": "n", "sample": "n",
    "events": "events", "cases": "events", "x": "events", "count": "events",
    "group": "group", "subgroup": "group", "category": "group", "arm": "group",
    "moderator": "moderator", "mod": "moderator", "covariate": "moderator",
    "year": "year", "date": "year", "pubyear": "year",
}
# `total` is ambiguous: it means the denominator for a single proportion, and a
# sample size for correlations. Resolved per-measure in _map_headers.


class MetaIngestError(Exception):
    """Raised when the file cannot be read or lacks the required columns."""


def _sanity(measure: str, s: dict) -> str | None:
    """Return a human-readable reason if a study's numbers are impossible, else None."""
    g = s.get
    if measure in ("or", "rr", "rd", "peto"):
        e1, n1, e2, n2 = g("e1"), g("n1"), g("e2"), g("n2")
        for e, n, lbl in ((e1, n1, "group 1"), (e2, n2, "group 2")):
            if e is None or n is None:
                continue
            if e < 0 or n <= 0:
                return f"events/N must be positive ({lbl})"
            if e > n:
                return f"events exceed N in {lbl} ({int(e)} > {int(n)})"
    elif measure in ("md", "smd"):
        for n, sd, lbl in ((g("n1"), g("sd1"), "group 1"), (g("n2"), g("sd2"), "group 2")):
            if n is not None and n < 2:
                return f"N must be at least 2 ({lbl})"
            if sd is not None and sd <= 0:
                return f"SD must be greater than 0 ({lbl})"
    elif measure == "fisher_z":
        r, n = g("r"), g("n")
        if r is not None and not (-1 < r < 1):
            return "correlation r must be between -1 and 1"
        if n is not None and n < 4:
            return "sample size must be at least 4"
    elif measure == "proportion":
        e, n = g("events"), g("total")
        if e is not None and n is not None and e > n:
            return f"events exceed total ({int(e)} > {int(n)})"
        if n is not None and n <= 0:
            return "total must be positive"
    elif measure in ("generic", "hr"):
        se = g("se")
        if se is not None and se <= 0:
            return "standard error must be greater than 0"
    return None


def _norm(s: object) -> str:
    return "".join(ch for ch in str(s).strip().lower()
                   if ch.isalnum())


def template_columns(measure: str, *, group=False, moderator=False, year=False) -> list[str]:
    """Canonical header row for a downloadable template."""
    cols = [c[1] for c in MEASURE_COLUMNS.get(measure, MEASURE_COLUMNS["generic"])]
    if group:
        cols.append("group")
    if moderator:
        cols.append("moderator")
    if year:
        cols.append("year")
    return cols


def required_keys(measure: str) -> list[str]:
    return [c[0] for c in MEASURE_COLUMNS.get(measure, MEASURE_COLUMNS["generic"])]


def _map_headers(headers: list[str], measure: str) -> dict[str, int]:
    """Map required/optional study keys to column indices using aliases."""
    wanted = set(required_keys(measure)) | {"group", "moderator", "year"}
    # generic also accepts 'variance' instead of 'se'
    if measure == "generic":
        wanted.add("variance")
    mapping: dict[str, int] = {}
    for idx, h in enumerate(headers):
        nh = _norm(h)
        key = _ALIASES.get(nh)
        # per-measure disambiguation of 'total'/'n'
        if nh == "total":
            key = "total" if measure == "proportion" else ("n" if measure == "fisher_z" else "total")
        if key and key in wanted and key not in mapping:
            mapping[key] = idx
    return mapping


def _to_float(x) -> float | None:
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if s == "" or s.lower() in ("nan", "na", "none", "null"):
        return None
    try:
        f = float(s)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def parse(path: str | Path, measure: str) -> dict:
    """Read a study spreadsheet and return studies + preview + validation.

    Returns a dict:
      {measure, n_rows, mapped_columns, missing_columns, studies (valid),
       invalid (list of {row, name, reason}), warnings, has_group/moderator/year}
    """
    measure = measure if measure in MEASURE_COLUMNS else "generic"
    try:
        df = read_dataframe(path)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise MetaIngestError(f"Could not read the file: {exc}") from exc

    if df.shape[0] == 0:
        raise MetaIngestError("The file has no data rows.")

    headers = [str(c) for c in df.columns]
    mapping = _map_headers(headers, measure)

    req = required_keys(measure)
    # generic can satisfy the effect-variance requirement with se OR variance
    missing = []
    for k in req:
        if k == "se" and measure == "generic":
            if "se" not in mapping and "variance" not in mapping:
                missing.append("standard_error (or variance)")
            continue
        if k not in mapping:
            # look up the canonical header label for the message
            label = next((c[1] for c in MEASURE_COLUMNS[measure] if c[0] == k), k)
            missing.append(label)
    if missing:
        raise MetaIngestError(
            "The file is missing required column(s) for this effect measure: "
            + ", ".join(missing)
            + ". Download the template to see the exact headers expected."
        )

    numeric_keys = [k for k in mapping if k not in ("name", "group")]
    rows = df.to_dict(orient="records")
    values = list(df.itertuples(index=False, name=None))

    studies: list[dict] = []
    invalid: list[dict] = []
    warnings: list[str] = []
    has_group = "group" in mapping
    has_moderator = "moderator" in mapping
    has_year = "year" in mapping

    for i, row in enumerate(values):
        rownum = i + 2  # +1 for header, +1 for 1-based display
        name_idx = mapping.get("name")
        name = str(row[name_idx]).strip() if name_idx is not None and row[name_idx] is not None else ""
        if not name or name.lower() == "nan":
            name = f"Study {i + 1}"

        study: dict = {"name": name}
        bad: str | None = None
        for k in numeric_keys:
            if k in ("moderator", "year"):
                continue  # optional numerics handled below (never fatal)
            v = _to_float(row[mapping[k]])
            if v is None:
                bad = f"missing or non-numeric '{k}'"
                break
            study[k] = v
        if bad is None and measure == "generic" and "se" not in study and "variance" in mapping:
            v = _to_float(row[mapping["variance"]])
            if v is not None:
                study["variance"] = v

        # optional descriptors
        if has_group and row[mapping["group"]] is not None:
            g = str(row[mapping["group"]]).strip()
            if g and g.lower() != "nan":
                study["group"] = g
        if has_moderator:
            mv = _to_float(row[mapping["moderator"]])
            if mv is not None:
                study["moderator"] = mv
        if has_year:
            yv = _to_float(row[mapping["year"]])
            if yv is not None:
                study["year"] = int(yv)

        if bad is None:
            bad = _sanity(measure, study)
        if bad is None:
            # final check: does this study yield a valid variance under the measure?
            try:
                yi, vi = meta_analysis._effect(measure, study)
                if vi <= 0 or math.isnan(vi):
                    bad = "produces a non-positive variance (check counts / SDs)"
            except Exception as exc:  # noqa: BLE001
                bad = str(exc)

        if bad is None:
            studies.append(study)
        else:
            invalid.append({"row": rownum, "name": name, "reason": bad})

    if len(studies) < 2:
        raise MetaIngestError(
            f"Only {len(studies)} valid study row(s) found — meta-analysis needs at "
            "least 2. Check the flagged rows below."
            if invalid else
            "Fewer than 2 valid studies were found in the file."
        )
    if invalid:
        warnings.append(
            f"{len(invalid)} row(s) were skipped because of problems (listed below). "
            f"{len(studies)} valid studies will be analysed."
        )

    mapped_columns = {k: headers[idx] for k, idx in mapping.items()}
    return {
        "measure": measure,
        "n_rows": int(df.shape[0]),
        "n_valid": len(studies),
        "mapped_columns": mapped_columns,
        "studies": studies,
        "invalid": invalid,
        "warnings": warnings,
        "has_group": has_group,
        "has_moderator": has_moderator,
        "has_year": has_year,
    }
