"""Docker sandbox runner.

Executes generated Python/R scripts inside an isolated Docker container with no
network access and a strict timeout. This layer contains NO AI — it only runs
what has already been previewed and confirmed.

STATUS: stub — signatures only. Implement file-by-file with review.
"""

from app.config import settings
from app.models.schemas import ExecutionResult, Language


def run_in_sandbox(
    script: str,
    language: Language,
    data_path: str,
    timeout_seconds: int | None = None,
) -> ExecutionResult:
    """Run a script inside the sandbox container and return the result.

    - No network inside the container.
    - Killed after `timeout_seconds` (defaults to settings.sandbox_timeout_seconds).
    - Artifacts are written to a mounted output directory and collected.
    """
    timeout = timeout_seconds or settings.sandbox_timeout_seconds
    raise NotImplementedError
