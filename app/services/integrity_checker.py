"""Integrity checker.

Validates an uploaded data file before anything else runs: readable format,
non-empty, columns detectable, no obvious corruption. Reports problems back to
the user rather than silently proceeding.

STATUS: stub — signatures only. Implement file-by-file with review.
"""

from pathlib import Path


def check_data_file(path: str | Path) -> dict:
    """Return a report on the uploaded data file.

    Returns a dict like:
        {"ok": bool, "issues": list[str], "columns": list[str], "n_rows": int}
    """
    raise NotImplementedError("integrity_checker.check_data_file not yet implemented")
