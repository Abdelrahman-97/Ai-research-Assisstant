"""Tests for the integrity checker."""

from pathlib import Path

import pandas as pd

from app.services import integrity_checker


def test_valid_csv(tmp_path: Path):
    p = tmp_path / "d.csv"
    pd.DataFrame({"group": ["a", "b", "a", "b"], "score": [1, 2, 3, 4]}).to_csv(p, index=False)

    report = integrity_checker.check_data_file(p)
    assert report.ok
    assert report.summary is not None
    assert report.summary.n_rows == 4
    assert report.summary.n_cols == 2
    names = {c.name for c in report.summary.columns}
    assert names == {"group", "score"}


def test_unreadable_file(tmp_path: Path):
    p = tmp_path / "x.parquet"
    p.write_text("not really parquet")
    report = integrity_checker.check_data_file(p)
    assert not report.ok
    assert report.issues


def test_empty_column_flagged(tmp_path: Path):
    p = tmp_path / "d.csv"
    pd.DataFrame({"a": [1, 2], "empty": [None, None]}).to_csv(p, index=False)
    report = integrity_checker.check_data_file(p)
    assert report.ok  # still usable
    assert any("empty" in issue.lower() for issue in report.issues)
