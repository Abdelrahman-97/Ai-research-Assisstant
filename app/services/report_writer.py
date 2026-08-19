"""Report writer (pipeline step 7: export the Results section to .docx and .pdf).

The AI works in Markdown throughout; conversion happens only here, at export.
The user can download either format. Both renderers cover what a Results section
actually uses: headings, paragraphs, bold/italic, bullet/numbered lists, and
embedded figure artifacts.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.shared import Inches
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as RLImage
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from app.models.schemas import Artifact

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\d+[.)]\s+(.*)$")
# NB: underscores are NOT treated as italics — research text and file names are
# full of them (e.g. descriptive_statistics.csv), and doing so mangled them.
# Backtick `code` spans are unwrapped to plain text.
_BOLD_ITALIC_RE = re.compile(r"(\*\*.+?\*\*|\*.+?\*|`.+?`)")


def _clean_latex(text: str) -> str:
    """Strip leftover LaTeX so it doesn't render as literal characters.

    The results prompt asks for plain text, but this is a safety net for any
    stray math markup the model still emits.
    """
    text = text.replace("$", "")
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", text)
    text = text.replace("\\times", "×").replace("\\le", "≤").replace("\\ge", "≥")
    text = text.replace("\\%", "%").replace("\\,", " ").replace("\\ ", " ")
    text = re.sub(r"\^\{?(-?\d+)\}?", r"^\1", text)  # keep exponents readable
    return text


def _add_runs_with_emphasis(paragraph, text: str) -> None:
    """Add text to a paragraph, honouring **bold** and *italic*; unwrap `code`."""
    text = _clean_latex(text)
    for part in _BOLD_ITALIC_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*"):
            paragraph.add_run(part[1:-1]).italic = True
        elif part.startswith("`") and part.endswith("`"):
            paragraph.add_run(part[1:-1])  # code -> plain text (keeps underscores)
        else:
            paragraph.add_run(part)


def markdown_to_docx(
    markdown: str,
    artifacts: list[Artifact],
    out_path: str | Path,
) -> Path:
    """Convert a Markdown Results section + figure artifacts into a .docx file."""
    doc = Document()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = min(len(heading.group(1)), 4)
            doc.add_heading(heading.group(2).strip(), level=level)
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

    # Append figures at the end, each with its caption.
    figures = [a for a in artifacts if a.kind == "figure" and Path(a.path).exists()]
    if figures:
        doc.add_heading("Figures", level=2)
        for fig in figures:
            try:
                doc.add_picture(fig.path, width=Inches(6))
            except Exception:  # noqa: BLE001 - skip unreadable images, keep the doc
                continue
            if fig.caption:
                caption = doc.add_paragraph()
                run = caption.add_run(fig.caption)
                run.italic = True

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def _md_inline_to_html(text: str) -> str:
    """Convert **bold** / *italic* to minimal HTML reportlab accepts; unwrap `code`.

    Underscores are left alone (they belong to file names / variables), and any
    stray LaTeX is stripped. Ampersand/angle brackets are escaped for reportlab.
    """
    text = _clean_latex(text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"\1", text)  # code -> plain text
    return text


def markdown_to_pdf(
    markdown: str,
    artifacts: list[Artifact],
    out_path: str | Path,
) -> Path:
    """Convert a Markdown Results section + figure artifacts into a .pdf file."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    story: list = []
    bullets: list = []

    def flush_bullets() -> None:
        if bullets:
            story.append(ListFlowable(list(bullets), bulletType="bullet"))
            bullets.clear()

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
            story.append(Paragraph(_md_inline_to_html(heading.group(2)), styles[f"Heading{level}"]))
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            bullets.append(ListItem(Paragraph(_md_inline_to_html(bullet.group(1)), styles["BodyText"])))
            continue

        numbered = _NUMBERED_RE.match(line)
        if numbered:
            flush_bullets()
            story.append(Paragraph(_md_inline_to_html(numbered.group(1)), styles["BodyText"]))
            continue

        flush_bullets()
        story.append(Paragraph(_md_inline_to_html(line), styles["BodyText"]))

    flush_bullets()

    figures = [a for a in artifacts if a.kind == "figure" and Path(a.path).exists()]
    if figures:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Figures", styles["Heading2"]))
        for fig in figures:
            try:
                story.append(RLImage(fig.path, width=6 * inch, height=4 * inch, kind="proportional"))
            except Exception:  # noqa: BLE001 - skip unreadable images
                continue
            if fig.caption:
                story.append(Paragraph(f"<i>{fig.caption}</i>", styles["BodyText"]))

    SimpleDocTemplate(str(out), pagesize=A4).build(story)
    return out
