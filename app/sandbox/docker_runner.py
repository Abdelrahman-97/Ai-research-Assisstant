"""Docker sandbox runner (pipeline step 5: execute the script in isolation).

Executes a generated Python/R script inside a Docker container with:
  - no network  (--network none)
  - a read-only-ish working directory mounted from the host
  - a strict wall-clock timeout
  - a non-root user (from the sandbox image)

This layer contains NO AI. It only runs what has already been previewed and
approved. Artifacts the script writes into `artifacts/` are collected and returned.

Dev fallback: if Docker isn't installed AND settings.sandbox_allow_subprocess_fallback
is True, the script runs in a plain subprocess instead. This removes the isolation
boundary, so it is OFF by default and must never be enabled in production.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config import settings
from app.models.schemas import Artifact, ExecutionResult, Language, RunStatus

_SCRIPT_NAME = {Language.python: "analysis.py", Language.r: "analysis.R"}
_INTERPRETER = {Language.python: "python", Language.r: "Rscript"}


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _prepare_workdir(workdir: Path, script: str, language: Language, data_path: str) -> str:
    """Lay out the working directory: script, data file, artifacts/. Returns data filename."""
    (workdir / "artifacts").mkdir(parents=True, exist_ok=True)
    (workdir / _SCRIPT_NAME[language]).write_text(script, encoding="utf-8")

    src = Path(data_path)
    data_filename = f"data{src.suffix.lower()}"
    shutil.copyfile(src, workdir / data_filename)
    return data_filename


def _collect_artifacts(workdir: Path) -> list[Artifact]:
    artifacts: list[Artifact] = []
    art_dir = workdir / "artifacts"
    if not art_dir.exists():
        return artifacts
    for f in sorted(art_dir.iterdir()):
        if not f.is_file():
            continue
        suffix = f.suffix.lower()
        kind = "figure" if suffix in {".png", ".jpg", ".jpeg", ".svg"} else (
            "table" if suffix in {".csv", ".tsv", ".xlsx"} else "raw"
        )
        artifacts.append(Artifact(kind=kind, path=str(f), caption=f.name))
    return artifacts


def _build_result(
    proc: subprocess.CompletedProcess, workdir: Path
) -> ExecutionResult:
    status = RunStatus.executed if proc.returncode == 0 else RunStatus.failed
    return ExecutionResult(
        status=status,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        exit_code=proc.returncode,
        artifacts=_collect_artifacts(workdir),
    )


def run_in_sandbox(
    script: str,
    language: Language,
    data_path: str,
    timeout_seconds: int | None = None,
) -> ExecutionResult:
    """Run a script inside the sandbox and return the result."""
    timeout = timeout_seconds or settings.sandbox_timeout_seconds

    with tempfile.TemporaryDirectory(prefix="ra_run_") as tmp:
        workdir = Path(tmp)
        data_filename = _prepare_workdir(workdir, script, language, data_path)

        if _docker_available():
            cmd = [
                "docker", "run", "--rm",
                "--network", "none",
                "--memory", "1g",
                "-v", f"{workdir}:/work",
                "-w", "/work",
                settings.sandbox_image,
                _INTERPRETER[language], _SCRIPT_NAME[language],
            ]
        elif settings.sandbox_allow_subprocess_fallback:
            # DEV ONLY — no isolation.
            cmd = [_INTERPRETER[language], _SCRIPT_NAME[language]]
        else:
            return ExecutionResult(
                status=RunStatus.failed,
                stderr=(
                    "Docker is not available and the subprocess fallback is "
                    "disabled. Install Docker and build the sandbox image, or set "
                    "SANDBOX_ALLOW_SUBPROCESS_FALLBACK=true for local dev only."
                ),
                exit_code=None,
            )

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                status=RunStatus.failed,
                stderr=f"Execution timed out after {timeout}s.",
                exit_code=None,
                artifacts=_collect_artifacts(workdir),
            )

        result = _build_result(proc, workdir)
        # Artifacts live in a temp dir that is about to be deleted — copy them
        # somewhere durable before returning.
        return _persist_artifacts(result)


def _persist_artifacts(result: ExecutionResult) -> ExecutionResult:
    """Copy collected artifacts out of the temp workdir into the data dir."""
    if not result.artifacts:
        return result
    out_dir = Path(settings.data_dir) / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    persisted: list[Artifact] = []
    for art in result.artifacts:
        src = Path(art.path)
        if not src.exists():
            continue
        dest = out_dir / src.name
        shutil.copyfile(src, dest)
        persisted.append(Artifact(kind=art.kind, path=str(dest), caption=art.caption))
    result.artifacts = persisted
    return result
