import io
import json
from pathlib import Path

import pytest

import send_user_file_worktree_root_gate

WORKTREE_CWD = "C:\\dev\\project\\.claude\\worktrees\\feature-branch"
SHARE_PATH = "Y:\\shared\\reports\\reflect.md"
SCRATCHPAD_PATH = "C:\\Users\\example\\AppData\\Local\\Temp\\claude\\scratchpad\\reflect.md"
SCRATCH_FOLDER_PATH = WORKTREE_CWD + "\\.scratch\\reflect.md"


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hook_input: dict[str, object],
) -> tuple[int, str]:
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = send_user_file_worktree_root_gate.main()
    return exit_code, capsys.readouterr().err


def send_user_file_input(all_files: object, cwd: object = WORKTREE_CWD) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "SendUserFile",
        "cwd": cwd,
        "tool_input": {"files": all_files, "status": "normal", "display": "render"},
    }


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


@pytest.mark.parametrize("outside_path", [SHARE_PATH, SCRATCHPAD_PATH])
def test_should_deny_a_file_outside_the_working_directory_and_name_the_scratch_folder(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], outside_path: str
) -> None:
    exit_code, block_reason = run_gate(monkeypatch, capsys, send_user_file_input([outside_path]))
    assert exit_code == 2
    assert outside_path in block_reason
    assert WORKTREE_CWD + "\\.scratch\\" in block_reason


@pytest.mark.parametrize(
    "inside_path",
    [
        SCRATCH_FOLDER_PATH,
        SCRATCH_FOLDER_PATH.lower(),
        SCRATCH_FOLDER_PATH.replace("\\", "/"),
        ".scratch\\reflect.md",
        WORKTREE_CWD,
    ],
)
def test_should_allow_a_file_under_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], inside_path: str
) -> None:
    assert run_gate(monkeypatch, capsys, send_user_file_input([inside_path])) == (0, "")


def test_should_deny_a_path_that_climbs_out_of_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    climbing_path = WORKTREE_CWD + "\\.scratch\\..\\..\\other-worktree\\reflect.md"
    exit_code, block_reason = run_gate(monkeypatch, capsys, send_user_file_input([climbing_path]))
    assert exit_code == 2
    assert climbing_path in block_reason


def test_should_deny_a_sibling_folder_that_shares_the_working_directory_prefix(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sibling_path = WORKTREE_CWD + "-copy\\reflect.md"
    exit_code, block_reason = run_gate(monkeypatch, capsys, send_user_file_input([sibling_path]))
    assert exit_code == 2
    assert sibling_path in block_reason


def test_should_name_only_the_outside_files_when_a_call_mixes_both(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, block_reason = run_gate(
        monkeypatch, capsys, send_user_file_input([SCRATCH_FOLDER_PATH, SHARE_PATH])
    )
    assert exit_code == 2
    assert SHARE_PATH in block_reason
    assert "- " + SCRATCH_FOLDER_PATH not in block_reason


def test_should_compare_posix_paths_under_a_posix_working_directory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    posix_cwd = "/home/user/worktree"
    assert run_gate(
        monkeypatch, capsys, send_user_file_input([posix_cwd + "/.scratch/a.md"], posix_cwd)
    ) == (0, "")
    exit_code, block_reason = run_gate(
        monkeypatch, capsys, send_user_file_input(["/tmp/a.md"], posix_cwd)
    )
    assert exit_code == 2
    assert "/tmp/a.md" in block_reason


@pytest.mark.parametrize(
    "hook_input",
    [
        send_user_file_input([SHARE_PATH], cwd=None),
        send_user_file_input([SHARE_PATH], cwd=""),
        send_user_file_input(None),
        send_user_file_input(SHARE_PATH),
        {**send_user_file_input([SHARE_PATH]), "tool_name": "Read"},
    ],
)
def test_should_allow_a_call_the_gate_cannot_judge(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hook_input: dict[str, object],
) -> None:
    assert run_gate(monkeypatch, capsys, hook_input) == (0, "")
