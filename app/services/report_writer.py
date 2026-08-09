"""Report writer (pipeline step 7: export the Results section to .docx).

The AI works in Markdown throughout; conversion to Word happens only here, at
export. This is a lightweight Markdown-to-docx renderer covering what a Results
section actually uses: headings, paragraphs, bold/italic, bullet/numbered lists,
and embedding figure artifacts. It deliberately avoids a heavyweight dependency.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.shared import Inches

from app.models.schemas import Artifact

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\d+[.)]\s+(.*)$")
_BOLD_ITALIC_RE = re.compile(r"(\*\*.+?\*\*|\*.+?\*|_.+?_)")


def _add_runs_with_emphasis(paragraph, text: str) -> None:
    """Add text to a paragraph, honouring **bold** and *italic* / _italic_."""
    for part in _BOLD_ITALIC_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*"):
            paragraph.add_run(part[1:-1]).italic = True
        elif part.startswith("_") and part.endswith("_"):
            paragraph.add_run(part[1:-1]).italic = True
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
