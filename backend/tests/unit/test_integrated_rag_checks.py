from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.core.config import Settings
from app.services.genai_verification import GenAiVerificationService, MockGenAiVerificationClient
from scripts.run_integrated_rag_checks import (
    CheckResult,
    CheckSpec,
    CheckStatus,
    build_check_plan,
    classify_process_result,
    exit_code_for,
    overall_status,
    run_plan,
)


def test_integrated_requirements_include_backend_and_rag_manifests() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    content = (repository_root / "requirements-integrated.txt").read_text(encoding="utf-8")

    assert "-r backend/requirements.txt" in content
    assert "-r rag/requirements.txt" in content


def test_integrated_check_plan_covers_backend_and_rag_validation() -> None:
    plan = build_check_plan(sys.executable)
    names = [spec.name for spec in plan]

    assert names == [
        "backend_compile",
        "backend_import",
        "backend_pytest",
        "backend_openapi",
        "backend_checks",
        "backend_demo_pipeline",
        "real_rag_import",
        "rag_pytest",
    ]
    assert all(spec.command[0] == sys.executable for spec in plan)
    assert next(spec for spec in plan if spec.name == "real_rag_import").dependency_gate is True
    assert next(spec for spec in plan if spec.name == "rag_pytest").command[-2:] == ("tests/rag", "-q")


def test_missing_rag_dependency_is_reported_as_blocked() -> None:
    spec = CheckSpec("real_rag_import", (sys.executable, "-c", "pass"), Path.cwd(), dependency_gate=True)
    completed = subprocess.CompletedProcess(
        spec.command,
        returncode=1,
        stdout="",
        stderr="ModuleNotFoundError: No module named 'tiktoken'\n",
    )

    result = classify_process_result(spec, completed)

    assert result.status == CheckStatus.BLOCKED
    assert "tiktoken" in result.reason


def test_rag_tests_are_blocked_when_import_gate_fails(tmp_path: Path) -> None:
    marker = tmp_path / "rag-tests-ran"
    plan = [
        CheckSpec(
            "real_rag_import",
            (sys.executable, "-c", "raise ModuleNotFoundError(\"No module named 'tiktoken'\")"),
            tmp_path,
            dependency_gate=True,
        ),
        CheckSpec(
            "rag_pytest",
            (sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"),
            tmp_path,
        ),
    ]

    results = run_plan(plan)

    assert [result.status for result in results] == [CheckStatus.BLOCKED, CheckStatus.BLOCKED]
    assert not marker.exists()
    assert overall_status(results) == CheckStatus.BLOCKED
    assert exit_code_for(CheckStatus.BLOCKED) == 2


def test_overall_status_fails_if_any_required_check_fails() -> None:
    results = [
        CheckResult("backend", CheckStatus.PASS, "ok", 0),
        CheckResult("rag", CheckStatus.FAIL, "tests failed", 1),
    ]

    assert overall_status(results) == CheckStatus.FAIL
    assert exit_code_for(CheckStatus.FAIL) == 1


def test_mock_genai_mode_does_not_construct_real_door2_client() -> None:
    service = GenAiVerificationService(settings=Settings(GENAI_MOCK_MODE="true"))

    assert isinstance(service.client, MockGenAiVerificationClient)
