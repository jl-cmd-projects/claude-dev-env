import subprocess
import tempfile
from pathlib import Path

import pytest

from hooks_constants.turn_review_gate_constants import BLOCK_REASON_TEMPLATE
from turn_review_claim import (
    _claim_locked_stop,
    _is_wake_prompt,
    _JudgeRequest,
    _judge_requests,
    _locked_stop_wake,
    _prompt_baselines,
)
from turn_review_findings import JudgeVerdict
from turn_review_snapshot import working_tree_snapshot
from turn_review_state import _Finding, _load_state, _ReviewState, _save_state

SESSION_ID = "claim-session"
BASE_COMMIT = "a" * 40
TURN_COMMIT = "b" * 40
FINDING_TEXT = "src/service.py:3 - The diff drops the retry."


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_directory = tmp_path / "home"
    home_directory.mkdir()
    state_directory = tmp_path / "state"
    state_directory.mkdir()
    monkeypatch.setenv("HOME", str(home_directory))
    monkeypatch.setenv("USERPROFILE", str(home_directory))
    monkeypatch.setattr(tempfile, "tempdir", str(state_directory))
    return home_directory


def git(repository: Path, *all_arguments: str) -> str:
    return subprocess.run(
        ["git", *all_arguments], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repository_root = tmp_path / "app"
    repository_root.mkdir()
    git(repository_root, "init", "-q", "-b", "main")
    git(repository_root, "config", "user.email", "test@example.com")
    git(repository_root, "config", "user.name", "Test")
    (repository_root / "service.py").write_text("call()\n")
    git(repository_root, "add", "-A")
    git(repository_root, "commit", "-q", "-m", "start")
    return repository_root


def log_text(home_directory: Path) -> str:
    log_path = home_directory / ".claude" / "logs" / "turn-review.log"
    return log_path.read_text() if log_path.exists() else ""


def test_should_count_a_prompt_inside_the_wake_window_or_a_task_notification_as_the_wake() -> None:
    woken_state = _ReviewState(last_wake_at=1000.0)
    assert _is_wake_prompt(woken_state, "next task", 1009.9) is True
    assert _is_wake_prompt(woken_state, "next task", 1010.0) is False
    assert (
        _is_wake_prompt(_ReviewState(), "  <task-notification>done</task-notification>", 0.0)
        is True
    )
    assert _is_wake_prompt(_ReviewState(), "next task", 0.0) is False


def test_should_keep_the_saved_baseline_only_while_the_turn_is_open(repository: Path) -> None:
    saved_baselines = {str(repository): BASE_COMMIT}
    open_state = _ReviewState(all_baselines=saved_baselines, is_turn_open=True)
    assert _prompt_baselines(open_state, [repository]) == saved_baselines
    closed_state = _ReviewState(all_baselines=saved_baselines, is_turn_open=False)
    fresh_commit = _prompt_baselines(closed_state, [repository])[str(repository)]
    assert fresh_commit != BASE_COMMIT
    assert git(repository, "rev-parse", f"{fresh_commit}^") == git(repository, "rev-parse", "HEAD")


def test_should_judge_only_an_open_finding_in_a_reviewed_checkout(
    repository: Path, isolated_home: Path
) -> None:
    open_finding = _Finding(FINDING_TEXT, str(repository), BASE_COMMIT, TURN_COMMIT)
    review_state = _ReviewState(
        all_findings={
            "TR-1": open_finding,
            "TR-2": _Finding(FINDING_TEXT, str(repository), BASE_COMMIT, TURN_COMMIT, "dismissed"),
            "TR-3": _Finding(FINDING_TEXT, "/elsewhere/lib", BASE_COMMIT, TURN_COMMIT),
        }
    )
    all_reasons = {
        "TR-1": "The caller retries.",
        "TR-2": "Asked again.",
        "TR-3": "Other checkout.",
        "TR-9": "Unknown.",
    }
    assert _judge_requests(review_state, all_reasons, [repository], False) == [
        _JudgeRequest("TR-1", open_finding, "The caller retries.")
    ]
    assert _judge_requests(review_state, {"TR-1": "The caller retries."}, [repository], True) == []
    logged_text = log_text(isolated_home)
    assert "Dismiss TR-2 ignored: the finding is dismissed" in logged_text
    assert (
        "Dismiss TR-3 ignored: the finding is in a checkout this stop does not review"
        in logged_text
    )
    assert "Dismiss TR-9 ignored: the finding is not a finding of this session" in logged_text
    assert "Dismiss TR-1 waits: the hold cap is reached, so no judge ran" in logged_text


def test_should_claim_the_turn_range_once_and_move_the_baseline(repository: Path) -> None:
    base_commit = working_tree_snapshot(repository, None)
    assert base_commit is not None
    _save_state(
        SESSION_ID,
        _ReviewState(
            all_baselines={str(repository): base_commit}, blocks_in_a_row=2, is_turn_open=True
        ),
    )
    (repository / "service.py").write_text("call(1)\n")
    first_claim = _claim_locked_stop(SESSION_ID, [repository], {})
    claimed_state = _load_state(SESSION_ID)
    turn_commit = claimed_state.all_baselines[str(repository)]
    assert turn_commit != base_commit
    assert first_claim.all_turn_ranges == [(repository, base_commit, turn_commit)]
    assert claimed_state.is_turn_open is False
    assert claimed_state.blocks_in_a_row == 2
    second_claim = _claim_locked_stop(SESSION_ID, [repository], {})
    assert second_claim.all_turn_ranges == []
    assert _load_state(SESSION_ID).blocks_in_a_row == 0


def test_should_wake_with_the_rejections_in_id_order_and_the_new_findings(tmp_path: Path) -> None:
    repository_root = tmp_path / "app"
    _save_state(
        SESSION_ID,
        _ReviewState(
            blocks_in_a_row=1,
            all_findings={
                "TR-2": _Finding(FINDING_TEXT, str(repository_root), BASE_COMMIT, TURN_COMMIT),
                "TR-10": _Finding(FINDING_TEXT, str(repository_root), BASE_COMMIT, TURN_COMMIT),
            },
        ),
    )
    all_verdicts = {
        "TR-10": JudgeVerdict(is_approved=False, reason="Nothing retries.\n"),
        "TR-2": JudgeVerdict(is_approved=False, reason="The diff  still drops it. "),
    }
    wake_text = _locked_stop_wake(
        SESSION_ID,
        [(repository_root, BASE_COMMIT, TURN_COMMIT, ["src/service.py:9 - The update is lost."])],
        all_verdicts,
    )
    assert wake_text == (
        "Dismissal of TR-2 rejected: The diff still drops it. Fix it.\n"
        "Dismissal of TR-10 rejected: Nothing retries. Fix it.\n\n"
        + BLOCK_REASON_TEMPLATE.format(
            all_findings="app:\n[TR-11] src/service.py:9 - The update is lost."
        )
    )
    saved_state = _load_state(SESSION_ID)
    assert {each_id: each.status for each_id, each in saved_state.all_findings.items()} == {
        "TR-2": "upheld",
        "TR-10": "upheld",
        "TR-11": "open",
    }
    assert saved_state.blocks_in_a_row == 2
    assert saved_state.last_wake_at is not None


def test_should_dismiss_quietly_on_an_approval_and_keep_a_capped_hold_count(
    tmp_path: Path, isolated_home: Path
) -> None:
    approval = {"TR-1": JudgeVerdict(is_approved=True, reason="The caller retries.")}
    for each_blocks, each_expected_blocks in ((2, 0), (3, 3)):
        _save_state(
            SESSION_ID,
            _ReviewState(
                blocks_in_a_row=each_blocks,
                all_findings={
                    "TR-1": _Finding(FINDING_TEXT, str(tmp_path), BASE_COMMIT, TURN_COMMIT)
                },
            ),
        )
        assert _locked_stop_wake(SESSION_ID, [], approval) is None
        saved_state = _load_state(SESSION_ID)
        assert saved_state.all_findings["TR-1"].status == "dismissed"
        assert saved_state.all_findings["TR-1"].judge_reason == "The caller retries."
        assert saved_state.blocks_in_a_row == each_expected_blocks
        assert saved_state.last_wake_at is None
    assert "[turn_review_gate] TR-1 dismissed: The caller retries." in log_text(isolated_home)
