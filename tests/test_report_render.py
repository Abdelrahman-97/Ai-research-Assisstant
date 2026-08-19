"""Renderer tests — the fixes from the first real proof run.

Regression guards for: underscores in file names being mangled by italics, and
LaTeX leaking into the document as literal characters.
"""

from pathlib import Path

from docx import Document

from app.services import report_writer as rw


def test_clean_latex_strips_math():
    out = rw._clean_latex(r"mean was $147.08$ ($\text{SD} = 3.18$), p $\times 10^{-1}$")
    assert "$" not in out
    assert "\\text" not in out
    assert "147.08" in out and "SD = 3.18" in out
    assert "×" in out  # \times -> ×


def test_pdf_inline_preserves_underscores_and_unwraps_code():
    html = rw._md_inline_to_html("see `descriptive_statistics.csv` and **bold** value")
    assert "descriptive_statistics.csv" in html          # underscores intact
    assert "`" not in html                                # code unwrapped
    assert "<b>bold</b>" in html                          # bold kept
    assert "<i>" not in html                              # no accidental italics


def test_docx_keeps_filenames_and_drops_latex(tmp_path: Path):
    md = (
        "## Results\n\n"
        "The control group mean was $147.083$ ($\\text{SD} = 3.18$). "
        "See `descriptive_statistics.csv` and `assumption_checks.csv`.\n"
    )
    out = rw.markdown_to_docx(md, [], tmp_path / "r.docx")
    text = "\n".join(p.text for p in Document(str(out)).paragraphs)

    assert "descriptive_statistics.csv" in text   # not "descriptivestatistics.csv"
    assert "assumption_checks.csv" in text
    assert "$" not in text                         # LaTeX stripped
    assert "\\text" not in text
    assert "147.083" in text
