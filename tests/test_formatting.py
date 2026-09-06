"""Tests for output formatting: preset resolution, styled docx/pdf rendering,
template matching, and the consultation pricing add-on.
"""

import csv

import pytest
from docx import Document

from app.models.schemas import Artifact, DataSummary, FormatSpec, Scope
from app.services import formatting, pricing, report_writer


def _artifacts(tmp_path):
    csvp = tmp_path / "t.csv"
    with csvp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Group", "Mean", "p"])
        w.writerow(["A", "3.8", "<0.001"])
        w.writerow(["B", "2.1", ""])
    # a real PNG so both docx add_picture and reportlab RLImage can read it
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    png = tmp_path / "f.png"
    plt.figure(figsize=(3, 2)); plt.plot([1, 2, 3], [1, 4, 9]); plt.savefig(str(png)); plt.close()
    return [
        Artifact(kind="table", path=str(csvp), caption="Summary."),
        Artifact(kind="figure", path=str(png), caption="A figure."),
    ]


MD = "# Results\n\n## Primary outcome\n\nThe effect was **significant**.\n"


def test_resolve_presets():
    apa = formatting.resolve(FormatSpec(preset="apa"))
    assert apa.line_spacing == 2.0 and apa.heading_numbering is False
    two = formatting.resolve(FormatSpec(preset="two_column"))
    assert two.columns == 2
    # custom overrides layer on top
    c = formatting.resolve(FormatSpec(preset="standard", font_name="Arial", font_size_pt=11))
    assert c.font_name == "Arial" and c.font_size_pt == 11


@pytest.mark.parametrize("preset", ["standard", "apa", "vancouver", "two_column"])
def test_docx_and_pdf_render(tmp_path, preset):
    arts = _artifacts(tmp_path)
    fmt = formatting.resolve(FormatSpec(preset=preset, figure_start_number=5, table_start_number=3))
    dx = tmp_path / "o.docx"
    pf = tmp_path / "o.pdf"
    report_writer.markdown_to_docx(MD, arts, dx, fmt=fmt)
    report_writer.markdown_to_pdf(MD, arts, pf, fmt=fmt)
    assert dx.read_bytes()[:2] == b"PK"
    assert pf.read_bytes()[:4] == b"%PDF"
    d = Document(str(dx))
    assert len(d.tables) == 1                       # CSV became a real table
    text = "\n".join(p.text for p in d.paragraphs)
    assert "Table 3." in text and "Figure 5." in text   # start numbers honoured


def test_template_matching_inherits_styles(tmp_path):
    # build a "template" with a distinctive font, then render into it
    tpl = tmp_path / "tpl.docx"
    tdoc = Document()
    tdoc.styles["Normal"].font.name = "Georgia"
    tdoc.add_paragraph("placeholder")
    tdoc.save(str(tpl))

    fmt = formatting.resolve(FormatSpec(preset="template", template_blob_id="x"))
    out = tmp_path / "out.docx"
    report_writer.markdown_to_docx(MD, _artifacts(tmp_path), out, fmt=fmt, template_path=str(tpl))
    d = Document(str(out))
    assert d.styles["Normal"].font.name == "Georgia"      # inherited from template
    assert "placeholder" not in "\n".join(p.text for p in d.paragraphs)  # body cleared


def test_heading_numbering_toggle(tmp_path):
    on = formatting.resolve(FormatSpec(preset="standard"))       # numbered
    off = formatting.resolve(FormatSpec(preset="apa"))           # plain
    d_on = tmp_path / "on.docx"
    d_off = tmp_path / "off.docx"
    report_writer.markdown_to_docx(MD, [], d_on, fmt=on)
    report_writer.markdown_to_docx(MD, [], d_off, fmt=off)
    assert any(p.text.startswith("1") for p in Document(str(d_on)).paragraphs)
    assert not any(p.text.startswith("1  ") for p in Document(str(d_off)).paragraphs)


def _summary():
    return DataSummary(n_rows=100, n_cols=5, columns=[])


def test_docx_rtl_marks_paragraphs(tmp_path):
    from docx.oxml.ns import qn
    fmt = formatting.resolve(FormatSpec(preset="standard"))
    out = tmp_path / "ar.docx"
    report_writer.markdown_to_docx("# النتائج\n\nفقرة عربية.\n", [], out, fmt=fmt, rtl=True)
    d = Document(str(out))
    marked = 0
    for p in d.paragraphs:
        pPr = p._p.find(qn("w:pPr"))
        if pPr is not None and pPr.find(qn("w:bidi")) is not None:
            marked += 1
    assert marked >= 1   # at least the heading + paragraph carry RTL


class _FakeClient:
    def __init__(self):
        self.messages = None
    def chat(self, messages):
        self.messages = messages
        return "## النتائج\n\nتم."


def test_results_writer_arabic_prompt():
    from app.services import results_writer
    from app.models.schemas import ProposedTest, ExecutionResult, RunStatus
    fake = _FakeClient()
    test = ProposedTest(name="t-test", reasoning="two groups", variables=["g", "y"])
    ex = ExecutionResult(status=RunStatus.executed, stdout="t=4.9 p=0.001")
    out = results_writer.write_results(
        test=test, execution=ex, scope=Scope.studies, language="ar", client=fake
    )
    # Arabic system prompt + Arabic writing rule were used.
    system = fake.messages[0]["content"]
    user = fake.messages[1]["content"]
    assert "العربية" in system
    assert "العربية" in user
    assert out == "## النتائج\n\nتم."


def test_consultation_pricing():
    none = pricing.quote(scope=Scope.thesis, data_summary=_summary(), n_tests=3, word_count=800)
    review = pricing.quote(scope=Scope.thesis, data_summary=_summary(), n_tests=3,
                           word_count=800, consultation="review")
    full = pricing.quote(scope=Scope.thesis, data_summary=_summary(), n_tests=3,
                         word_count=800, consultation="full")
    assert review.amount_egp == none.amount_egp + 500
    assert full.amount_egp == none.amount_egp + 3000
    assert full.consultation == "full"
