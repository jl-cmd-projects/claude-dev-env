"""Check scoring boundaries that could otherwise inflate evaluation results."""

import argparse
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "review_eval", Path(__file__).with_name("run.py")
)
RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)
GRADING = __import__("review_eval_support.grading", fromlist=["grading"])
EXECUTION = __import__("review_eval_support.execution", fromlist=["execution"])
ACCOUNT = __import__("review_eval_support.account", fromlist=["account"])

CODEX_BINARY = "codex-under-test"
CODEX_HOME_VARIABLE = "CODEX_HOME"
BROKER_HOME = str(Path("profiles-root") / "codex-1")
WAIT_REASON = "no account has room; next reset at 2026-11-10T00:00:00Z"
FREE_PLAN_REASON = "default is on a free plan; the broker never picks it"
NO_ACCOUNT_FAILURE = "no_codex_account"


def finding(line=2, category="falsy-zero"):
    return {
        "line": line,
        "category": category,
        "failure_scenario": "zero gets replaced by three",
    }


def test_duplicate_findings_do_not_inflate_recall() -> None:
    case = RUN.cases()[0]
    grade_record = RUN.grade(case, {"findings": [finding(), finding()]})
    assert grade_record == {"tp": 1, "fp": 1, "fn": 0, "pass": False, "clean": False}


def test_wrong_location_counts_as_miss_and_false_alarm() -> None:
    grade_record = RUN.grade(RUN.cases()[0], {"findings": [finding(line=1)]})
    assert (grade_record["tp"], grade_record["fp"], grade_record["fn"]) == (0, 1, 1)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"findings": [finding(line=True)]},
        {"findings": [finding(category="style")]},
        {"findings": [{**finding(), "failure_scenario": " "}]},
    ],
)
def test_invalid_output_is_not_scored(response) -> None:
    with pytest.raises(ValueError):
        RUN.grade(RUN.cases()[0], response)


def test_infrastructure_failure_is_not_a_task_failure() -> None:
    summary = RUN.summarize([{"status": "infra_error"}])
    assert summary["scored"] == 0
    assert summary["pass_rate"] is None
    assert summary["infra_errors"] == 1


def test_heldout_groups_and_witnesses() -> None:
    values = RUN.cases()
    assert len(values) == 16
    for case in values:
        RUN.verify_witness(case)
        assert (
            json.dumps(case["expected"]) not in GRADING.prompt(case, "review")
            or not case["expected"]
        )


def test_clean_controls_expose_false_positives() -> None:
    case = RUN.cases()[1]
    row = {"status": "scored", "grade": RUN.grade(case, {"findings": [finding()]})}
    summary = RUN.summarize([row])
    assert summary["false_positive_rate"] == 1
    assert summary["specificity"] == 0


@pytest.mark.parametrize(
    "events",
    [
        [],
        [{"type": "thread.started"}],
        [
            {"type": "thread.started"},
            {"type": "turn.completed"},
            {"item": {"type": "command_execution"}},
        ],
    ],
)
def test_incomplete_or_tool_using_trace_is_rejected(events) -> None:
    with pytest.raises(ValueError):
        GRADING.validate_trace(events, {"findings": []})


def test_trace_and_saved_response_must_match() -> None:
    events = [
        {"type": "thread.started"},
        {"type": "turn.completed"},
        {"item": {"type": "agent_message", "text": '{"findings":[]}'}},
    ]
    GRADING.validate_trace(events, {"findings": []})
    with pytest.raises(ValueError):
        GRADING.validate_trace(events, {"findings": [finding()]})


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"status": "infra_error"}],
        [{"status": "output_error"}],
        [{"status": "scored", "grade": {"pass": False}}],
    ],
)
def test_unsuccessful_evaluation_exits_nonzero(rows) -> None:
    assert RUN.evaluation_exit_code(rows) == 1


def broker_answer(tier, home, reason="codex-1 has 62% left"):
    return json.dumps(
        {
            "decision": {
                "action": "wait" if tier == "wait" else "run",
                "account": "codex-1",
                "profile": "codex-1",
                "home": home,
                "reason": reason,
                "tier": tier,
                "resets_at": None,
            },
            "accounts": [],
            "state_path": "state.json",
        }
    )


class CallRecorder:
    def __init__(self, broker_exit_code=0, broker_stdout="", broker_error=None):
        self.broker_exit_code = broker_exit_code
        self.broker_stdout = broker_stdout
        self.broker_error = broker_error
        self.all_broker_commands = []
        self.all_codex_calls = []

    def __call__(self, command, **keywords):
        if command[0] == CODEX_BINARY:
            self.all_codex_calls.append((command, keywords))
            return self._codex_result(command)
        self.all_broker_commands.append(command)
        if self.broker_error:
            raise self.broker_error
        return subprocess.CompletedProcess(
            command, self.broker_exit_code, self.broker_stdout, ""
        )

    def _codex_result(self, command):
        reply = {"findings": []}
        reply_path = Path(command[command.index("--output-last-message") + 1])
        reply_path.write_text(json.dumps(reply), encoding="utf-8")
        all_events = [
            {"type": "thread.started"},
            {"type": "turn.completed"},
            {"item": {"type": "agent_message", "text": json.dumps(reply)}},
        ]
        stdout = "\n".join(json.dumps(each_event) for each_event in all_events)
        return subprocess.CompletedProcess(command, 0, stdout, "")


@pytest.fixture(autouse=True)
def no_exported_codex_home(monkeypatch) -> None:
    monkeypatch.delenv(CODEX_HOME_VARIABLE, raising=False)


def run_live_attempt(recorder, monkeypatch, record_root) -> dict:
    monkeypatch.setattr(subprocess, "run", recorder)
    settings = argparse.Namespace(
        model="model-under-test", effort="low", codex=CODEX_BINARY, timeout=5
    )
    return EXECUTION.execute(RUN.cases()[0], settings, record_root, "review recipe")


def test_live_attempt_runs_on_the_home_the_broker_names(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EVAL_MARKER", "kept")
    recorder = CallRecorder(broker_stdout=broker_answer("normal", BROKER_HOME))

    attempt = run_live_attempt(recorder, monkeypatch, tmp_path)

    assert attempt["status"] == "scored"
    assert len(recorder.all_codex_calls) == 1
    _, codex_keywords = recorder.all_codex_calls[0]
    assert codex_keywords["env"][CODEX_HOME_VARIABLE] == BROKER_HOME
    assert codex_keywords["env"]["EVAL_MARKER"] == "kept"
    assert recorder.all_broker_commands[0][2:] == ["choose", "--product", "codex", "--require-tier", "normal"]


def test_exported_codex_home_runs_on_the_home_the_broker_answers(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(CODEX_HOME_VARIABLE, "exported-home")
    recorder = CallRecorder(broker_stdout=broker_answer("normal", BROKER_HOME))

    attempt = run_live_attempt(recorder, monkeypatch, tmp_path)

    assert attempt["status"] == "scored"
    assert [each[2:] for each in recorder.all_broker_commands] == [
        ["choose", "--product", "codex", "--home", "exported-home"]
    ]
    _, codex_keywords = recorder.all_codex_calls[0]
    assert codex_keywords["env"][CODEX_HOME_VARIABLE] == BROKER_HOME


def test_padded_exported_codex_home_runs_on_the_home_the_broker_answers(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(CODEX_HOME_VARIABLE, "  exported-home  ")
    recorder = CallRecorder(broker_stdout=broker_answer("normal", BROKER_HOME))

    attempt = run_live_attempt(recorder, monkeypatch, tmp_path)

    assert attempt["status"] == "scored"
    assert [each[2:] for each in recorder.all_broker_commands] == [
        ["choose", "--product", "codex", "--home", "exported-home"]
    ]
    _, codex_keywords = recorder.all_codex_calls[0]
    assert codex_keywords["env"][CODEX_HOME_VARIABLE] == BROKER_HOME


def test_exported_codex_home_on_a_low_room_paid_account_still_runs(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(CODEX_HOME_VARIABLE, "exported-home")
    recorder = CallRecorder(
        broker_stdout=broker_answer("luna", "exported-home", "default has 4% left")
    )

    attempt = run_live_attempt(recorder, monkeypatch, tmp_path)

    assert attempt["status"] == "scored"


@pytest.mark.parametrize(
    ("broker_exit_code", "broker_stdout"),
    [
        (3, broker_answer("wait", None, FREE_PLAN_REASON)),
        (2, "cannot read account list"),
        (0, "not json"),
    ],
)
def test_exported_codex_home_the_broker_refuses_stops_before_any_model_call(
    monkeypatch, tmp_path, broker_exit_code, broker_stdout
) -> None:
    monkeypatch.setenv(CODEX_HOME_VARIABLE, "exported-home")
    recorder = CallRecorder(broker_exit_code, broker_stdout)

    attempt = run_live_attempt(recorder, monkeypatch, tmp_path)

    assert attempt["status"] == "infra_error"
    assert attempt["failure"] == NO_ACCOUNT_FAILURE
    assert recorder.all_codex_calls == []
    assert list(tmp_path.iterdir()) == []


def test_blank_codex_home_does_not_count_as_a_choice(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(CODEX_HOME_VARIABLE, "  ")
    recorder = CallRecorder(broker_stdout=broker_answer("normal", BROKER_HOME))

    run_live_attempt(recorder, monkeypatch, tmp_path)

    _, codex_keywords = recorder.all_codex_calls[0]
    assert codex_keywords["env"][CODEX_HOME_VARIABLE] == BROKER_HOME


@pytest.mark.parametrize(
    ("broker_exit_code", "broker_stdout"),
    [
        (3, broker_answer("wait", None, WAIT_REASON)),
        (0, broker_answer("luna", BROKER_HOME, "codex-1 has 4% left")),
        (2, "cannot read account list"),
        (0, ""),
        (0, "not json"),
        (0, "[]"),
        (0, broker_answer("normal", None)),
        (0, broker_answer("normal", "")),
    ],
)
def test_unusable_broker_answer_stops_before_any_model_call(
    monkeypatch, tmp_path, broker_exit_code, broker_stdout
) -> None:
    recorder = CallRecorder(broker_exit_code, broker_stdout)

    attempt = run_live_attempt(recorder, monkeypatch, tmp_path)

    assert attempt["status"] == "infra_error"
    assert attempt["failure"] == NO_ACCOUNT_FAILURE
    assert recorder.all_codex_calls == []
    assert list(tmp_path.iterdir()) == []


def test_wait_answer_reports_the_broker_reason(monkeypatch, tmp_path) -> None:
    recorder = CallRecorder(3, broker_answer("wait", None, WAIT_REASON))

    attempt = run_live_attempt(recorder, monkeypatch, tmp_path)

    assert WAIT_REASON in attempt["detail"]


@pytest.mark.parametrize(
    "broker_error",
    [subprocess.TimeoutExpired("broker", 150), OSError("interpreter missing")],
)
def test_broker_that_cannot_run_stops_before_any_model_call(
    monkeypatch, tmp_path, broker_error
) -> None:
    recorder = CallRecorder(broker_error=broker_error)

    attempt = run_live_attempt(recorder, monkeypatch, tmp_path)

    assert attempt["status"] == "infra_error"
    assert attempt["failure"] == NO_ACCOUNT_FAILURE
    assert recorder.all_codex_calls == []


GIT_NOT_IGNORED_EXIT_CODE = 1
GIT_NOT_A_REPOSITORY_EXIT_CODE = 128


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_every_support_module_can_be_tracked_by_git() -> None:
    support_directory = Path(__file__).with_name("review_eval_support")
    all_modules = sorted(str(each) for each in support_directory.rglob("*.py"))

    completed = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", *all_modules],
        cwd=support_directory,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode == GIT_NOT_A_REPOSITORY_EXIT_CODE:
        pytest.skip("the suite is not inside a git work tree")
    assert completed.returncode == GIT_NOT_IGNORED_EXIT_CODE


def test_broker_script_is_found_beside_the_package() -> None:
    broker_script = ACCOUNT.broker_script(ACCOUNT.default_broker_candidates())

    assert broker_script.is_file()
    assert broker_script.name == "account_broker.py"


def test_broker_script_prefers_the_first_candidate_that_exists(tmp_path) -> None:
    missing_script = tmp_path / "missing" / "account_broker.py"
    first_script = tmp_path / "first" / "account_broker.py"
    second_script = tmp_path / "second" / "account_broker.py"
    for each_script in (first_script, second_script):
        each_script.parent.mkdir()
        each_script.write_text("", encoding="utf-8")

    chosen = ACCOUNT.broker_script((missing_script, first_script, second_script))

    assert chosen == first_script


def test_missing_broker_script_refuses_the_run(tmp_path) -> None:
    with pytest.raises(ACCOUNT.CodexAccountUnavailable):
        ACCOUNT.broker_script((tmp_path / "account_broker.py",))
