"""Report writer.

Takes the Markdown Results section (grounded in sandbox artifacts) and exports
a Word (.docx) document. The AI works in Markdown throughout; conversion happens
only at export.

STATUS: stub — signatures only. Implement file-by-file with review.
"""

from pathlib import Path

from app.models.schemas import Artifact


def markdown_to_docx(
    markdown: str, artifacts: list[Artifact], out_path: str | Path
) -> Path:
    """Convert a Markdown Results section + artifacts into a .docx file."""
    raise NotImplementedError
