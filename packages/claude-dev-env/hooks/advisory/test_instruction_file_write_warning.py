"""The write-time warning names each instruction-budget finding after an instruction file is written."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).with_name("instruction_file_write_warning.py")


def _run_hook(file_path: Path) -> str:
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(file_path)}}
    completed = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _additional_context(stdout: str) -> str:
    return json.loads(stdout)["hookSpecificOutput"]["additionalContext"]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_write_outside_the_instruction_set_is_silent(tmp_path: Path) -> None:
    (tmp_path / "instruction-budget.json").write_text('{"max_launch_bytes": 1}', encoding="utf-8")
    guide_path = _write(tmp_path / "docs" / "guide.md", "x" * 500)
    assert _run_hook(guide_path) == ""


def test_an_instruction_file_in_a_repository_without_a_budget_is_silent(tmp_path: Path) -> None:
    agents_path = _write(tmp_path / "AGENTS.md", "x" * 500)
    assert _run_hook(agents_path) == ""


def test_a_clean_instruction_file_is_silent(tmp_path: Path) -> None:
    (tmp_path / "instruction-budget.json").write_text(
        '{"max_launch_bytes": 1000, "max_link_hops": 2}', encoding="utf-8"
    )
    agents_path = _write(tmp_path / "AGENTS.md", "# Clean\n")
    assert _run_hook(agents_path) == ""


def test_an_over_budget_instruction_file_gets_a_budget_warning(tmp_path: Path) -> None:
    (tmp_path / "instruction-budget.json").write_text(
        '{"max_launch_bytes": 10, "max_link_hops": 2}', encoding="utf-8"
    )
    agents_path = _write(tmp_path / "AGENTS.md", "x" * 50)
    context = _additional_context(_run_hook(agents_path))
    assert "[instruction-budget]" in context
    assert "over the cap of 10" in context


def test_a_skill_file_does_not_get_the_repository_budget_warning(tmp_path: Path) -> None:
    (tmp_path / "instruction-budget.json").write_text('{"max_launch_bytes": 10}', encoding="utf-8")
    _write(tmp_path / "AGENTS.md", "x" * 50)
    skill_path = _write(tmp_path / "skills" / "demo" / "SKILL.md", "# Demo\n")
    assert _run_hook(skill_path) == ""


@pytest.mark.parametrize(
    "read_error",
    [PermissionError("denied"), ValueError("outside the root"), RecursionError("deep")],
)
def test_a_read_error_during_the_check_stays_silent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    read_error: Exception,
) -> None:
    spec = importlib.util.spec_from_file_location("hook_under_test", HOOK_PATH)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    (tmp_path / "instruction-budget.json").write_text('{"max_launch_bytes": 10}', encoding="utf-8")
    agents_path = _write(tmp_path / "AGENTS.md", "x")

    def raise_read_error(*_args: object) -> list:
        raise read_error

    monkeypatch.setattr(hook, "check_repository", raise_read_error)
    monkeypatch.setattr(
        hook,
        "read_hook_input_dictionary_from_stdin",
        lambda: {"tool_input": {"file_path": str(agents_path)}},
    )
    hook.main()
    assert capsys.readouterr().out == ""


def test_a_too_deep_instruction_file_gets_a_nesting_warning(tmp_path: Path) -> None:
    (tmp_path / "instruction-budget.json").write_text(
        '{"max_launch_bytes": 100000, "max_link_hops": 1}', encoding="utf-8"
    )
    _write(tmp_path / "AGENTS.md", "[one](one.md)\n")
    _write(tmp_path / "one.md", "[deep](deep/AGENTS.md)\n")
    deep_path = _write(tmp_path / "deep" / "AGENTS.md", "# Deep\n")
    context = _additional_context(_run_hook(deep_path))
    assert "[instruction-nesting]" in context
    assert "deep/AGENTS.md" in context
