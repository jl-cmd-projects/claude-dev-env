"""Check the eval's judge call with a stub claude: the row it stores, the command, and resume."""

import json
from pathlib import Path

from judge_eval_support import calls


def test_should_store_the_gated_flags_cost_and_model_of_a_verdict(
    stub_claude, make_case, verdict_text, promise_text
) -> None:
    stub_path = stub_claude(verdict_text(promise_span=promise_text))
    row = calls.judge_case(
        make_case("set_a/one", "hold-promise"), str(stub_path), "haiku", "medium", 10
    )
    assert row["status"] == "ok"
    assert row["flags"] == [True, False]
    assert row["promise_span"] == promise_text
    assert row["cost_usd"] == 0.0004
    assert row["models"] == ["claude-haiku-4-5"]


def test_should_pass_the_model_and_effort_to_the_child(
    stub_claude, make_case, verdict_text, tmp_path: Path
) -> None:
    stub_path = stub_claude(verdict_text())
    calls.judge_case(
        make_case("set_a/one", "pass"), str(stub_path), "sonnet", "low", 10
    )
    call_line = (tmp_path / "stub.json.calls").read_text(encoding="utf-8")
    assert "--model sonnet" in call_line
    assert "--effort low" in call_line


def test_should_swap_only_the_model_and_effort_in_the_shipped_command() -> None:
    command = calls.call_command("/bin/claude", "sonnet", "low")
    assert command[0] == "/bin/claude"
    assert command[command.index("--model") + 1] == "sonnet"
    assert command[command.index("--effort") + 1] == "low"
    assert "--no-session-persistence" in command


def test_should_drop_the_list_flag_when_the_prompt_asks_for_a_list(
    stub_claude, make_case, verdict_text
) -> None:
    reply = "Open calls:\n- one\n- two\n- three"
    stub_path = stub_claude(verdict_text(list_span="Open calls:"))
    case = make_case(
        "set_a/one", "pass", reply=reply, prompt="List the open calls as bullets."
    )
    assert calls.judge_case(case, str(stub_path), "haiku", "medium", 10)["flags"] == [
        False,
        False,
    ]


def test_should_mark_a_span_outside_the_reply_as_a_shape_row(
    stub_claude, make_case, verdict_text
) -> None:
    stub_path = stub_claude(verdict_text(promise_span="a sentence the reply never had"))
    row = calls.judge_case(
        make_case("set_a/one", "hold-promise"), str(stub_path), "haiku", "medium", 10
    )
    assert row["status"] == "shape"
    assert row["flags"] == [False, False]


def test_should_mark_an_exit_code_and_is_error_as_error_rows(
    stub_claude, make_case, verdict_text
) -> None:
    case = make_case("set_a/one", "pass")
    exit_row = calls.judge_case(
        case, str(stub_claude(verdict_text(), exit_code=3)), "haiku", "medium", 10
    )
    error_row = calls.judge_case(
        case, str(stub_claude(verdict_text(), is_error=True)), "haiku", "medium", 10
    )
    assert (exit_row["status"], exit_row["error"]) == ("error", "exit code 3")
    assert (error_row["status"], error_row["error"]) == ("error", "is_error")


def test_should_skip_scored_calls_and_retry_errors_until_the_attempts_run_out(
    make_case,
) -> None:
    all_cases = [make_case("set_a/one", "pass"), make_case("set_a/two", "pass")]
    all_stored_rows = [
        {"id": "set_a/one", "run": 0, "digest": "d1", "status": "ok"},
        {"id": "set_a/two", "run": 0, "digest": "d1", "status": "error"},
        {"id": "set_a/two", "run": 1, "digest": "d1", "status": "error"},
        {"id": "set_a/two", "run": 1, "digest": "d1", "status": "error"},
        {"id": "set_a/one", "run": 1, "digest": "old", "status": "ok"},
    ]
    pending = calls.pending_calls(all_cases, all_stored_rows, "d1", runs=2, attempts=2)
    assert [(each_case["id"], each_run) for each_case, each_run in pending] == [
        ("set_a/two", 0),
        ("set_a/one", 1),
    ]


def test_should_append_one_tagged_row_per_call(
    stub_claude, make_case, verdict_text, tmp_path: Path
) -> None:
    stub_path = stub_claude(verdict_text())
    call_log_path = tmp_path / "results.jsonl"
    settings = {
        "claude_path": str(stub_path),
        "model": "haiku",
        "effort": "medium",
        "timeout_seconds": 10,
        "digest": "d1",
    }
    calls.run_calls(
        [(make_case("set_a/one", "pass"), 0), (make_case("set_a/two", "pass"), 2)],
        settings,
        call_log_path,
        2,
    )
    all_rows = calls.read_call_rows(call_log_path)
    assert sorted((each["id"], each["run"], each["digest"]) for each in all_rows) == [
        ("set_a/one", 0, "d1"),
        ("set_a/two", 2, "d1"),
    ]


def test_should_read_a_json_list_and_a_jsonl_file(tmp_path: Path) -> None:
    (tmp_path / "rows.json").write_text(json.dumps([{"id": "a"}]), encoding="utf-8")
    (tmp_path / "rows.jsonl").write_text(
        '{"id": "b"}\n\n{"id": "c"}\n', encoding="utf-8"
    )
    assert calls.read_cases(tmp_path / "rows.json") == [{"id": "a"}]
    assert calls.read_cases(tmp_path / "rows.jsonl") == [{"id": "b"}, {"id": "c"}]
    assert calls.read_call_rows(tmp_path / "absent.jsonl") == []


def test_should_change_the_digest_with_the_cases_or_the_model(tmp_path: Path) -> None:
    cases_path = tmp_path / "rows.json"
    cases_path.write_text("[]", encoding="utf-8")
    first = calls.run_digest(cases_path, "haiku", "medium")
    assert calls.run_digest(cases_path, "sonnet", "medium") != first
    cases_path.write_text('[{"id": "a"}]', encoding="utf-8")
    assert calls.run_digest(cases_path, "haiku", "medium") != first
