"""Add hooks/blocking and hooks/ to sys.path for every test collected under this directory."""

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Callable

import pytest

_BLOCKING_DIRECTORY = str(Path(__file__).resolve().parent)
_HOOKS_DIRECTORY = str(Path(_BLOCKING_DIRECTORY).parent)
for each_directory in (_BLOCKING_DIRECTORY, _HOOKS_DIRECTORY):
    if each_directory not in sys.path:
        sys.path.insert(0, each_directory)

_HOOK_INFRASTRUCTURE_TAIL = Path("packages") / "claude-dev-env" / "hooks" / "blocking"


@pytest.fixture
def hook_blocking_dir() -> Iterator[Path]:
    """Build a temporary tree whose tail mirrors a production hook directory.

    ``is_hook_infrastructure`` matches on the path tail, so a target inside
    the yielded directory routes the way a
    ``packages/claude-dev-env/hooks/blocking`` target does.
    """
    base_directory = Path(tempfile.mkdtemp())
    blocking_directory = base_directory / _HOOK_INFRASTRUCTURE_TAIL
    blocking_directory.mkdir(parents=True)
    try:
        yield blocking_directory
    finally:
        shutil.rmtree(base_directory, ignore_errors=False)


@pytest.fixture
def three_operation_patch() -> str:
    """Build a patch naming one update, one add, and one delete section."""
    return (
        "*** Begin Patch\n"
        "*** Update File: updated.py\n"
        "@@\n"
        "-before\n"
        "+after\n"
        " keep\n"
        "*** Add File: added.py\n"
        "+new\n"
        "*** Delete File: deleted.py\n"
        "*** End of File\n"
        "*** End Patch"
    )


@pytest.fixture
def init_bare_git_repo() -> Callable[[Path], None]:
    """Return a helper that initializes an empty git repository at a given path.

    The PII scanner reads an apply_patch payload's ``cwd`` as a git
    repository root, so a dispatcher-level apply_patch test needs a real
    repository there rather than a bare temp directory.
    """

    def _init_bare_git_repo(repository_root: Path) -> None:
        repository_root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=repository_root, check=True, capture_output=True)

    return _init_bare_git_repo


@pytest.fixture
def synthetic_github_token() -> str:
    """Return a fixture-only GitHub token shape, safe to embed in test payloads."""
    return "ghp_" + ("C" * 36)


@pytest.fixture
def multi_edit_payload() -> Callable[[str, list[dict[str, str]]], str]:
    """Return a helper that builds a MultiEdit tool payload JSON string."""

    def _multi_edit_payload(file_path: str, all_edits: list[dict[str, str]]) -> str:
        return json.dumps(
            {
                "tool_name": "MultiEdit",
                "tool_input": {"file_path": file_path, "edits": all_edits},
            }
        )

    return _multi_edit_payload


UNPINNED_WHICH = shutil.which
STUB_SCRIPT_TEMPLATE = """#!{python}
import json, os, pathlib, sys, time
state = pathlib.Path(os.environ["JUDGE_STUB_STATE"])
record = {{
    "argv": sys.argv[1:],
    "stdin": sys.stdin.read(),
    "cwd_entries": os.listdir(os.getcwd()),
    "review_child": os.environ.get("CLAUDE_TURN_REVIEW_CHILD"),
    "disable_claude_mds": os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS"),
    "disable_auto_memory": os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"),
    "parent_session_id": os.environ.get("CLAUDE_CODE_SESSION_ID"),
}}
with (state / "calls.jsonl").open("a") as calls:
    calls.write(json.dumps(record) + "\\n")
time.sleep(float((state / "sleep.txt").read_text()))
sys.stdout.write((state / "answer.txt").read_text())
sys.exit(int((state / "exit.txt").read_text()))
"""


class JudgeStub:
    """The state folder a stub ``claude`` reads its answer from and writes its calls to."""

    def __init__(self, state_folder: Path) -> None:
        self.state_folder = state_folder
        self.answer(
            verdict={
                "promised_report": False,
                "promise_span": "",
                "decisions_as_list": False,
                "list_span": "",
            }
        )
        (state_folder / "sleep.txt").write_text("0")
        (state_folder / "exit.txt").write_text("0")

    def answer(
        self,
        verdict: dict[str, object] | None = None,
        result: str | None = None,
        **all_outer_fields: object,
    ) -> None:
        result_text = result if result is not None else json.dumps(verdict)
        outer_answer = {
            "type": "result",
            "is_error": False,
            "result": result_text,
            **all_outer_fields,
        }
        (self.state_folder / "answer.txt").write_text(json.dumps(outer_answer))

    def raw_stdout(self, stdout_text: str) -> None:
        (self.state_folder / "answer.txt").write_text(stdout_text)

    def sleep(self, seconds: float) -> None:
        (self.state_folder / "sleep.txt").write_text(str(seconds))

    def exit_code(self, code: int) -> None:
        (self.state_folder / "exit.txt").write_text(str(code))

    def calls(self) -> list[dict[str, object]]:
        calls_path = self.state_folder / "calls.jsonl"
        if not calls_path.is_file():
            return []
        return [json.loads(each_line) for each_line in calls_path.read_text().splitlines()]


@pytest.fixture
def judge_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> JudgeStub:
    """Put a stub ``claude`` first on PATH that records each call and prints the answer the test sets."""
    executable_folder = tmp_path / "bin"
    executable_folder.mkdir()
    stub_path = executable_folder / "claude"
    stub_path.write_text(STUB_SCRIPT_TEMPLATE.format(python=sys.executable))
    stub_path.chmod(0o755)
    state_folder = tmp_path / "state"
    state_folder.mkdir()
    monkeypatch.setenv("PATH", str(executable_folder))
    monkeypatch.setattr(shutil, "which", UNPINNED_WHICH)
    monkeypatch.setenv("JUDGE_STUB_STATE", str(state_folder))
    return JudgeStub(state_folder)
