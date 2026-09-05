"""Report writer (pipeline step 7: export the Results section to .docx and .pdf).

The AI works in Markdown throughout; conversion happens only here, at export.
The output is styled according to a ResolvedFormat (font, size, line spacing,
heading numbering, one/two columns, caption placement, and figure/table start
numbers). When the user chose "match my document", the .docx is written *into a
copy of their uploaded template* so it inherits that document's own styles.

What a Results section actually uses is covered: headings, paragraphs,
bold/italic, bullet/numbered lists, data tables (from CSV artifacts) rendered as
real Word/PDF tables with numbered captions, and figures with numbered legends.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image as RLImage, ListFlowable, ListItem,
    PageTemplate, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.models.schemas import Artifact
from app.services.formatting import ResolvedFormat, resolve

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\d+[.)]\s+(.*)$")
_BOLD_ITALIC_RE = re.compile(r"(\*\*.+?\*\*|\*.+?\*|`.+?`)")

_MAX_TABLE_ROWS = 200   # guard against a runaway CSV becoming a giant table


def _clean_latex(text: str) -> str:
    text = text.replace("$", "")
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", text)
    text = text.replace("\\times", "×").replace("\\le", "≤").replace("\\ge", "≥")
    text = text.replace("\\%", "%").replace("\\,", " ").replace("\\ ", " ")
    text = re.sub(r"\^\{?(-?\d+)\}?", r"^\1", text)
    return text


def _read_csv(path: str) -> tuple[list[str], list[list[str]]]:
    """Read a CSV artifact into (headers, rows), capped for safety."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except Exception:  # noqa: BLE001
        return [], []
    if not rows:
        return [], []
    headers = rows[0]
    body = rows[1 : 1 + _MAX_TABLE_ROWS]
    return headers, body


def _split_artifacts(
    artifacts: list[Artifact],
) -> tuple[list[tuple[list[str], list[list[str]], str]], list[tuple[str, str]]]:
    """Return (tables, figures). tables=[(headers,rows,caption)], figures=[(path,caption)]."""
    tables: list[tuple[list[str], list[list[str]], str]] = []
    figures: list[tuple[str, str]] = []
    for a in artifacts:
        if a.kind == "table" and Path(a.path).exists():
            headers, rows = _read_csv(a.path)
            if headers:
                tables.append((headers, rows, a.caption or ""))
        elif a.kind == "figure" and Path(a.path).exists():
            figures.append((a.path, a.caption or ""))
    return tables, figures


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #
def _add_runs_with_emphasis(paragraph, text: str) -> None:
    text = _clean_latex(text)
    for part in _BOLD_ITALIC_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*"):
            paragraph.add_run(part[1:-1]).italic = True
        elif part.startswith("`") and part.endswith("`"):
            paragraph.add_run(part[1:-1])
        else:
            paragraph.add_run(part)


def _apply_base_style(doc: Document, fmt: ResolvedFormat) -> None:
    """Set the Normal style's font, size, and line spacing (preset/custom modes)."""
    try:
        style = doc.styles["Normal"]
        style.font.name = fmt.font_name
        # Ensure the font applies to all script ranges, not just Latin.
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = rpr.makeelement(qn("w:rFonts"), {})
            rpr.append(rfonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs"):
            rfonts.set(qn(attr), fmt.font_name)
        style.font.size = Pt(fmt.font_size_pt)
        pf = style.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = fmt.line_spacing
    except Exception:  # noqa: BLE001 - never let styling abort the export
        pass


def _set_columns(doc: Document, columns: int) -> None:
    if columns <= 1:
        return
    try:
        sectPr = doc.sections[0]._sectPr
        cols = sectPr.find(qn("w:cols"))
        if cols is None:
            cols = sectPr.makeelement(qn("w:cols"), {})
            sectPr.append(cols)
        cols.set(qn("w:num"), str(columns))
    except Exception:  # noqa: BLE001
        pass


def _clear_body(doc: Document) -> None:
    """Remove all body content but keep the final section properties (sectPr)."""
    body = doc.element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def _caption(doc: Document, text: str) -> None:
    try:
        p = doc.add_paragraph(text, style="Caption")
    except Exception:  # noqa: BLE001 - template may lack a Caption style
        p = doc.add_paragraph()
        p.add_run(text).italic = True


def _heading_prefix(counters: dict[int, int], level: int) -> str:
    counters[level] = counters.get(level, 0) + 1
    for deeper in [k for k in counters if k > level]:
        counters[deeper] = 0
    parts = [str(counters[l]) for l in range(1, level + 1) if counters.get(l)]
    return ".".join(parts) + "  " if parts else ""


def _add_table_docx(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    try:
        table.style = "Table Grid"
    except Exception:  # noqa: BLE001 - fall back to default table style
        pass
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(str(h))
        run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for i in range(len(headers)):
            cells[i].text = str(row[i]) if i < len(row) else ""


def markdown_to_docx(
    markdown: str,
    artifacts: list[Artifact],
    out_path: str | Path,
    *,
    fmt: ResolvedFormat | None = None,
    template_path: str | Path | None = None,
) -> Path:
    """Convert a Markdown Results section + artifacts into a styled .docx."""
    fmt = fmt or resolve(None)

    if template_path and Path(template_path).exists():
        doc = Document(str(template_path))   # inherit the user's own styles
        _clear_body(doc)
    else:
        doc = Document()
        _apply_base_style(doc, fmt)
        _set_columns(doc, fmt.columns)

    counters: dict[int, int] = {}
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = min(len(heading.group(1)), 4)
            text = heading.group(2).strip()
            if fmt.heading_numbering:
                text = _heading_prefix(counters, level) + text
            doc.add_heading(text, level=level)
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            p = doc.add_paragraph(style="List Bullet")
            _add_runs_with_emphasis(p, bullet.group(1))
            continue

        numbered = _NUMBERED_RE.match(line)
        if numbered:
            p = doc.add_paragraph(style="List Number")
            _add_runs_with_emphasis(p, numbered.group(1))
            continue

        p = doc.add_paragraph()
        _add_runs_with_emphasis(p, line)

    tables, figures = _split_artifacts(artifacts)

    # Tables (captioned, numbered from the chosen start).
    tnum = fmt.table_start_number
    for headers, rows, cap in tables:
        label = f"Table {tnum}." + (f" {cap}" if cap else "")
        if fmt.caption_above_table:
            _caption(doc, label)
            _add_table_docx(doc, headers, rows)
        else:
            _add_table_docx(doc, headers, rows)
            _caption(doc, label)
        doc.add_paragraph()
        tnum += 1

    # Figures (image + numbered legend below).
    fnum = fmt.figure_start_number
    img_width = Inches(3.0 if fmt.columns >= 2 else 6.0)
    for path, cap in figures:
        try:
            doc.add_picture(path, width=img_width)
        except Exception:  # noqa: BLE001 - skip unreadable images
            continue
        label = f"Figure {fnum}." + (f" {cap}" if cap else "")
        _caption(doc, label)
        fnum += 1

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
_FONT_MAP = {
    "times new roman": ("Times-Roman", "Times-Bold", "Times-Italic"),
    "times": ("Times-Roman", "Times-Bold", "Times-Italic"),
    "arial": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique"),
    "helvetica": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique"),
    "calibri": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique"),
}


def _md_inline_to_html(text: str) -> str:
    text = _clean_latex(text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text


def markdown_to_pdf(
    markdown: str,
    artifacts: list[Artifact],
    out_path: str | Path,
    *,
    fmt: ResolvedFormat | None = None,
) -> Path:
    """Convert a Markdown Results section + artifacts into a styled .pdf."""
    fmt = fmt or resolve(None)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    base_font, bold_font, italic_font = _FONT_MAP.get(
        fmt.font_name.lower(), ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique")
    )
    size = fmt.font_size_pt
    leading = size * fmt.line_spacing

    body = ParagraphStyle(
        "Body", fontName=base_font, fontSize=size, leading=leading, spaceAfter=6,
    )
    cap = ParagraphStyle(
        "Cap", fontName=italic_font, fontSize=max(size - 1, 8),
        leading=(size) * 1.1, spaceAfter=8,
    )
    heads = {
        i: ParagraphStyle(
            f"H{i}", fontName=bold_font, fontSize=size + max(5 - i, 0),
            leading=(size + max(5 - i, 0)) * 1.2, spaceBefore=10, spaceAfter=6,
        )
        for i in range(1, 5)
    }

    story: list = []
    bullets: list = []

    def flush_bullets() -> None:
        if bullets:
            story.append(ListFlowable(list(bullets), bulletType="bullet"))
            bullets.clear()

    counters: dict[int, int] = {}
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            flush_bullets()
            story.append(Spacer(1, 6))
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush_bullets()
            level = min(len(heading.group(1)), 4)
            text = heading.group(2).strip()
            if fmt.heading_numbering:
                text = _heading_prefix(counters, level) + text
            story.append(Paragraph(_md_inline_to_html(text), heads[level]))
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            bullets.append(ListItem(Paragraph(_md_inline_to_html(bullet.group(1)), body)))
            continue

        numbered = _NUMBERED_RE.match(line)
        if numbered:
            flush_bullets()
            story.append(Paragraph(_md_inline_to_html(numbered.group(1)), body))
            continue

        flush_bullets()
        story.append(Paragraph(_md_inline_to_html(line), body))

    flush_bullets()

    tables, figures = _split_artifacts(artifacts)

    tnum = fmt.table_start_number
    for headers, rows, caption in tables:
        label = f"Table {tnum}." + (f" {caption}" if caption else "")
        if fmt.caption_above_table:
            story.append(Paragraph(_md_inline_to_html(label), cap))
        data = [headers] + rows
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), bold_font),
            ("FONTNAME", (0, 1), (-1, -1), base_font),
            ("FONTSIZE", (0, 0), (-1, -1), max(size - 1, 8)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(t)
        if not fmt.caption_above_table:
            story.append(Paragraph(_md_inline_to_html(label), cap))
        story.append(Spacer(1, 10))
        tnum += 1

    fnum = fmt.figure_start_number
    fig_w = (3.0 if fmt.columns >= 2 else 6.0) * inch
    for path, caption in figures:
        try:
            story.append(RLImage(path, width=fig_w, height=fig_w * 0.66, kind="proportional"))
        except Exception:  # noqa: BLE001
            continue
        label = f"Figure {fnum}." + (f" {caption}" if caption else "")
        story.append(Paragraph(_md_inline_to_html(label), cap))
        fnum += 1

    # One or two columns.
    if fmt.columns >= 2:
        doc = BaseDocTemplate(str(out), pagesize=A4, leftMargin=0.6 * inch,
                              rightMargin=0.6 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch)
        gap = 0.3 * inch
        col_w = (doc.width - gap) / 2
        f1 = Frame(doc.leftMargin, doc.bottomMargin, col_w, doc.height, id="c1")
        f2 = Frame(doc.leftMargin + col_w + gap, doc.bottomMargin, col_w, doc.height, id="c2")
        doc.addPageTemplates([PageTemplate(id="two", frames=[f1, f2])])
        doc.build(story)
    else:
        SimpleDocTemplate(str(out), pagesize=A4).build(story)
    return out
