"""Statistics executor.

Turns a confirmed statistical test into a Python or R script, shows the script
to the user for MANDATORY preview, then runs it inside the sandbox (non-AI,
isolated). Collects artifacts (tables, figures, raw output).

STATUS: stub — signatures only. Implement file-by-file with review.
"""

from app.models.schemas import ExecutionResult, Language, ProposedTest


def generate_script(
    test: ProposedTest, data_path: str, language: Language
) -> str:
    """Generate the analysis script. Returned for mandatory preview before run."""
    raise NotImplementedError


def execute(script: str, language: Language, data_path: str) -> ExecutionResult:
    """Run the (already previewed) script in the sandbox and collect artifacts."""
    raise NotImplementedError
