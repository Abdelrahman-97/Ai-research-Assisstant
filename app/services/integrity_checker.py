"""Integrity checker (pipeline step 1: validate the uploaded data).

Reads an uploaded data file (Excel or CSV), checks it is usable, and produces a
compact summary of the columns. This summary — not the raw file — is what gets
sent to the AI for planning, so the model reasons about structure without us
shipping the entire dataset.

Reports problems back to the caller rather than silently proceeding.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.models.schemas import ColumnSummary, DataSummary, IntegrityReport

# How many example values to show per column in the summary.
_SAMPLE_VALUES = 5


def read_dataframe(path: str | Path) -> pd.DataFrame:
    """Load a .xlsx/.xls/.csv/.tsv file into a DataFrame."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(p)
    if suffix == ".csv":
        return pd.read_csv(p)
    if suffix == ".tsv":
        return pd.read_csv(p, sep="\t")
    raise ValueError(f"Unsupported data file type: {suffix or '(none)'}")


def summarize(df: pd.DataFrame) -> DataSummary:
    """Build a compact, model-friendly summary of a DataFrame.

    n_rows / n_cols reflect the full file, but the per-column detail is capped
    (settings.max_summary_columns) so a very wide file can't blow up the prompt.
    """
    from app.config import settings

    columns: list[ColumnSummary] = []
    for name in df.columns[: settings.max_summary_columns]:
        series = df[name]
        samples = (
            series.dropna().unique()[:_SAMPLE_VALUES].tolist()
        )
        columns.append(
            ColumnSummary(
                name=str(name),
                dtype=str(series.dtype),
                non_null=int(series.notna().sum()),
                n_unique=int(series.nunique(dropna=True)),
                sample_values=[str(v) for v in samples],
            )
        )
    return DataSummary(n_rows=int(len(df)), n_cols=int(df.shape[1]), columns=columns)


def check_data_file(path: str | Path) -> IntegrityReport:
    """Validate the uploaded data file and summarize it.

    Returns an IntegrityReport: ok=False with issues if the file can't be used,
    otherwise ok=True with a DataSummary.
    """
    issues: list[str] = []

    try:
        df = read_dataframe(path)
    except Exception as exc:  # noqa: BLE001 - any read failure is a user-facing issue
        return IntegrityReport(ok=False, issues=[f"Could not read the file: {exc}"])

    if df.shape[0] == 0:
        issues.append("The file has no data rows.")
    if df.shape[1] == 0:
        issues.append("The file has no columns.")

    # Unnamed columns usually mean a missing/duplicated header row.
    unnamed = [str(c) for c in df.columns if str(c).startswith("Unnamed")]
    if unnamed:
        issues.append(
            f"{len(unnamed)} column(s) have no header — check the header row."
        )

    # Fully empty columns are worth flagging (won't break, but likely a mistake).
    empty_cols = [str(c) for c in df.columns if df[c].notna().sum() == 0]
    if empty_cols:
        issues.append(f"Column(s) entirely empty: {', '.join(empty_cols)}")

    summary = summarize(df)
    # Empty/columnless files are hard failures; the rest are warnings that still
    # let the user proceed if they choose.
    ok = df.shape[0] > 0 and df.shape[1] > 0
    return IntegrityReport(ok=ok, issues=issues, summary=summary)
