from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CheckSpec:
    name: str
    command: tuple[str, ...]
    cwd: Path
    dependency_gate: bool = False


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    reason: str
    returncode: int | None


def build_check_plan(python_executable: str = sys.executable) -> list[CheckSpec]:
    """Return the complete deterministic integrated-validation plan."""
    # Do not resolve the executable symlink: backend/.venv/bin/python commonly
    # points at /usr/bin/python, and resolving it would discard the venv.
    python = str(Path(python_executable).absolute())
    return [
        CheckSpec("backend_compile", (python, "-m", "compileall", "app", "scripts"), BACKEND_ROOT),
        CheckSpec(
            "backend_import",
            (python, "-c", "from app.main import app; print(app.title, app.version, len(app.openapi()['paths']))"),
            BACKEND_ROOT,
        ),
        CheckSpec("backend_pytest", (python, "-m", "pytest", "-q"), BACKEND_ROOT),
        CheckSpec("backend_openapi", (python, "scripts/validate_openapi.py"), BACKEND_ROOT),
        CheckSpec("backend_checks", (python, "scripts/run_backend_checks.py"), BACKEND_ROOT),
        CheckSpec("backend_demo_pipeline", (python, "scripts/run_demo_pipeline.py"), BACKEND_ROOT),
        CheckSpec(
            "real_rag_import",
            (
                python,
                "-c",
                "from rag.api import retrieve_evidence, verify_claim; print('rag imports ok')",
            ),
            REPOSITORY_ROOT,
            dependency_gate=True,
        ),
        CheckSpec("rag_pytest", (python, "-m", "pytest", "tests/rag", "-q"), REPOSITORY_ROOT),
    ]


def classify_process_result(spec: CheckSpec, completed: subprocess.CompletedProcess[str]) -> CheckResult:
    """Classify a subprocess result without hiding missing optional dependencies."""
    if completed.returncode == 0:
        return CheckResult(spec.name, CheckStatus.PASS, "command completed successfully", 0)

    combined_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if spec.dependency_gate and (
        "ModuleNotFoundError" in combined_output
        or "No module named" in combined_output
        or "ImportError" in combined_output
    ):
        reason = _last_nonempty_line(combined_output) or "RAG dependencies are unavailable"
        return CheckResult(spec.name, CheckStatus.BLOCKED, reason, completed.returncode)

    reason = _last_nonempty_line(combined_output) or f"command exited with {completed.returncode}"
    return CheckResult(spec.name, CheckStatus.FAIL, reason, completed.returncode)


def overall_status(results: Sequence[CheckResult]) -> CheckStatus:
    if any(result.status == CheckStatus.FAIL for result in results):
        return CheckStatus.FAIL
    if any(result.status == CheckStatus.BLOCKED for result in results):
        return CheckStatus.BLOCKED
    return CheckStatus.PASS


def exit_code_for(status: CheckStatus) -> int:
    return {CheckStatus.PASS: 0, CheckStatus.FAIL: 1, CheckStatus.BLOCKED: 2}[status]


def _last_nonempty_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _print_completed_output(completed: subprocess.CompletedProcess[str]) -> None:
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n", file=sys.stderr)


def run_plan(
    plan: Sequence[CheckSpec],
    *,
    environment: Mapping[str, str] | None = None,
) -> list[CheckResult]:
    env = dict(os.environ if environment is None else environment)
    results: list[CheckResult] = []
    rag_import_ready = True

    for spec in plan:
        if spec.name == "rag_pytest" and not rag_import_ready:
            result = CheckResult(
                spec.name,
                CheckStatus.BLOCKED,
                "real_rag_import did not pass; install requirements-integrated.txt before running RAG tests",
                None,
            )
            results.append(result)
            print(f"CHECK {result.name}: {result.status.value} — {result.reason}")
            continue

        print(f"$ ({spec.cwd}) {' '.join(spec.command)}", flush=True)
        completed = subprocess.run(
            list(spec.command),
            cwd=spec.cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        _print_completed_output(completed)
        result = classify_process_result(spec, completed)
        results.append(result)
        print(f"CHECK {result.name}: {result.status.value} — {result.reason}")
        if spec.name == "real_rag_import":
            rag_import_ready = result.status == CheckStatus.PASS

    return results


def main() -> int:
    results = run_plan(build_check_plan())
    status = overall_status(results)
    print("\nIntegrated Backend + RAG validation summary")
    for result in results:
        print(f"- {result.name}: {result.status.value} — {result.reason}")
    print(f"INTEGRATED_VALIDATION_RESULT={status.value}")
    return exit_code_for(status)


if __name__ == "__main__":
    raise SystemExit(main())
