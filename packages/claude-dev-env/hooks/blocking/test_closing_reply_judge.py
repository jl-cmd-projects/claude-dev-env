from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hooks_constants.closing_reply_judge_constants import JUDGE_PROMPT_TEMPLATE

if TYPE_CHECKING:
    from conftest import JudgeStub
from closing_reply_judge import (
    JudgeVerdict,
    child_environment,
    gated_verdict,
    is_judge_available,
    judge_command,
    judge_input,
    judge_prompt,
    judged_verdict,
    log_no_verdict,
    parsed_verdict,
)

PROMISE_REPLY = "Pushed the branch. The benchmark table will be posted when you get back."
PROMISE_SPAN = "The benchmark table will be posted when you get back."
LIST_REPLY = "Open calls:\n- keep the cache\n- drop the flag\n- rename the job"
LIST_SPAN = "Open calls:"


@pytest.fixture(autouse=True)
def judge_log_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def _log_text(tmp_path: Path) -> str:
    log_path = tmp_path / "home" / ".claude" / "logs" / "closing-reply-judge.log"
    return log_path.read_text() if log_path.is_file() else ""


def test_should_send_only_the_summary_line_for_a_task_notification() -> None:
    notification = "<task-notification>\n<task-id>a1</task-id>\n<summary>Lint job ended</summary>\n<result>long output</result>\n</task-notification>"
    assert judge_input(notification, "Done.", False) == {
        "prompt_kind": "task_notification",
        "user_prompt": "Lint job ended",
        "reply": "Done.",
        "question_tool_used": False,
        "list_scope": "Done.",
    }


def test_should_send_the_list_check_the_reply_without_its_in_progress_footer() -> None:
    footer_reply = "Shipped.\n\nIn progress:\n- I am fixing the list reader.\n- I am watching the ledger."
    all_input_fields = judge_input("Fix the build", footer_reply, False)
    assert all_input_fields["reply"] == footer_reply
    assert all_input_fields["list_scope"].strip() == "Shipped."


def test_should_drop_a_list_span_from_the_footer_and_keep_the_promise() -> None:
    footer_reply = "I will send a summary later.\n\nIn progress:\n- I am fixing the list reader.\n- I am watching the ledger.\n- I am shipping 8590."
    verdict_text = json.dumps(
        {
            "promised_report": True,
            "promise_span": "I will send a summary later.",
            "decisions_as_list": True,
            "list_span": "In progress:",
        }
    )
    assert parsed_verdict(verdict_text, footer_reply) == JudgeVerdict("I will send a summary later.", "")
    prose_heading_reply = f"See In progress: below.\n\n{footer_reply}"
    assert parsed_verdict(verdict_text, prose_heading_reply) == JudgeVerdict("I will send a summary later.", "")


def test_should_keep_a_decision_list_under_an_in_progress_heading_in_the_body() -> None:
    decisions_reply = (
        "In progress:\n- Should I delete the backup?\n- Should I merge 8590?\n- Should I close 8693?\n\n"
        "Pick one when you are back."
    )
    verdict_text = json.dumps(
        {"promised_report": False, "promise_span": "", "decisions_as_list": True, "list_span": "In progress:"}
    )
    assert parsed_verdict(verdict_text, decisions_reply) == JudgeVerdict("", "In progress:")


def test_should_keep_a_decision_list_in_an_in_progress_footer_of_asks() -> None:
    ask_reply = "Shipped.\n\nIn progress:\n- Approve the release.\n- Pick a price.\n- Confirm the date."
    asking_reply = (
        "Shipped.\n\nIn progress:\n- I am shipping 8590.\n- I am asking you to approve the release.\n"
        "- I am watching the ledger."
    )
    verdict_text = json.dumps(
        {"promised_report": False, "promise_span": "", "decisions_as_list": True, "list_span": "In progress:"}
    )
    assert judge_input("Fix the build", ask_reply, False)["list_scope"] == ask_reply
    assert parsed_verdict(verdict_text, ask_reply) == JudgeVerdict("", "In progress:")
    assert parsed_verdict(verdict_text, asking_reply) == JudgeVerdict("", "")
    holding_reply = (
        "Shipped.\n\nIn progress:\n- I am holding the release for your approval.\n"
        "- I am holding the price change for your approval.\n- I am holding the date for your approval."
    )
    assert parsed_verdict(verdict_text, holding_reply) == JudgeVerdict("", "In progress:")
    answer_reply = (
        "Shipped.\n\nIn progress:\n- I need an answer on the price.\n"
        "- I need an answer on the date.\n- I need an answer on the deposit."
    )
    assert parsed_verdict(verdict_text, answer_reply) == JudgeVerdict("", "In progress:")
    request_reply = (
        "Shipped.\n\nIn progress:\n- I am preparing the rollout. Pick a release date.\n"
        "- I am drafting the notice. Pick a sender.\n- I am pricing the plan. Pick a tier."
    )
    assert parsed_verdict(verdict_text, request_reply) == JudgeVerdict("", "In progress:")
    owner_reply = (
        "Shipped.\n\nIn progress:\n- I need the owner to pick the release date.\n"
        "- I need the owner to pick the sender.\n- I need the owner to pick the tier."
    )
    assert parsed_verdict(verdict_text, owner_reply) == JudgeVerdict("", "In progress:")
    choice_reply = (
        "Shipped.\n\nIn progress:\n- I am holding the sale until the owner picks a date.\n"
        "- I am holding the notice until the owner picks a sender.\n"
        "- I am holding the plan until the owner picks a tier."
    )
    assert parsed_verdict(verdict_text, choice_reply) == JudgeVerdict("", "In progress:")
    semicolon_reply = (
        "Shipped.\n\nIn progress:\n- I am preparing the launch; please pick a date.\n"
        "- I am drafting the notice; please pick a sender.\n- I am pricing the plan; please pick a tier."
    )
    assert parsed_verdict(verdict_text, semicolon_reply) == JudgeVerdict("", "In progress:")
    owner_input_reply = (
        "Shipped.\n\nIn progress:\n- I need a date from the owner.\n"
        "- I need a price from the owner.\n- I need a plan name from the owner."
    )
    assert parsed_verdict(verdict_text, owner_input_reply) == JudgeVerdict("", "In progress:")
    sequenced_reply = (
        "Shipped.\n\nIn progress:\n- I am preparing the launch. Next, choose its date.\n"
        "- I am pricing the plan. Then, pick the price.\n- I am painting the logo. Finally, select a color."
    )
    assert parsed_verdict(verdict_text, sequenced_reply) == JudgeVerdict("", "In progress:")
    coordinated_reply = (
        "Shipped.\n\nIn progress:\n- I am listing the dates so you can see them and pick one.\n"
        "- I am listing the prices so you can read them and choose one.\n"
        "- I am listing the logos so you can see them and then select one."
    )
    assert parsed_verdict(verdict_text, coordinated_reply) == JudgeVerdict("", "In progress:")
    benefit_reply = (
        "Shipped.\n\nIn progress:\n- I am updating the discount ledger so your prices stay current.\n"
        "- I am watching the export so your files arrive on time.\n"
        "- I am refreshing the cache so your pages load fast."
    )
    assert parsed_verdict(verdict_text, benefit_reply) == JudgeVerdict("", "")
    one_ask_reply = (
        "Shipped.\n\nIn progress:\n- I am shipping 8590.\n- I am merging 8790 once it has your approval.\n"
        "- I am watching the ledger."
    )
    assert parsed_verdict(verdict_text, one_ask_reply) == JudgeVerdict("", "")
    body_list_reply = (
        "In progress:\n- Should I delete the backup?\n- Should I merge 8590?\n- Should I close 8693?\n\n"
        "Pick one when you are back.\n\nIn progress:\n- I am shipping 8590.\n- I am merging 8790 once it has your approval."
    )
    assert parsed_verdict(verdict_text, body_list_reply) == JudgeVerdict("", "In progress:")


def test_should_tell_the_judge_to_read_the_asks_kept_under_in_progress() -> None:
    assert "Judge every list in list_scope, those footer lines included." in " ".join(
        JUDGE_PROMPT_TEMPLATE.split()
    )


def test_should_send_the_command_name_and_args_for_a_slash_command() -> None:
    command_prompt = "<command-message>review</command-message>\n<command-name>/review</command-name>\n<command-args>12 --fast</command-args>"
    all_input_fields = judge_input(command_prompt, "Done.", True)
    assert all_input_fields["prompt_kind"] == "slash_command"
    assert all_input_fields["user_prompt"] == "/review 12 --fast"
    assert all_input_fields["question_tool_used"] is True


def test_should_cut_a_typed_prompt_at_four_thousand_characters() -> None:
    long_prompt = "a" * 3990 + "b" * 50
    all_input_fields = judge_input(long_prompt, "Done.", False)
    assert all_input_fields["prompt_kind"] == "typed"
    assert all_input_fields["user_prompt"] == "a" * 3990 + "b" * 10


def test_should_put_the_input_json_in_place_of_the_data_marker() -> None:
    full_prompt = judge_prompt("Fix the build", PROMISE_REPLY, False)
    assert "$DATA" not in full_prompt
    assert (
        json.dumps(judge_input("Fix the build", PROMISE_REPLY, False), ensure_ascii=False, indent=1)
        in full_prompt
    )


def test_should_start_the_judge_with_hooks_and_mcp_disabled() -> None:
    all_command_parts = judge_command("/opt/claude")
    assert all_command_parts[:6] == ["/opt/claude", "-p", "--model", "haiku", "--effort", "medium"]
    assert (
        all_command_parts[all_command_parts.index("--settings") + 1] == '{"disableAllHooks": true}'
    )
    assert "--strict-mcp-config" in all_command_parts
    assert all_command_parts[all_command_parts.index("--mcp-config") + 1] == '{"mcpServers": {}}'
    assert all_command_parts[all_command_parts.index("--tools") + 1] == ""


def test_should_mark_the_child_and_drop_the_parent_session_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
    monkeypatch.setenv("JUDGE_TEST_KEPT", "kept")
    all_child_variables = child_environment()
    assert "CLAUDE_CODE_SESSION_ID" not in all_child_variables
    assert all_child_variables["JUDGE_TEST_KEPT"] == "kept"
    assert all_child_variables["CLAUDE_TURN_REVIEW_CHILD"] == "1"
    assert all_child_variables["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1"
    assert all_child_variables["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"


def test_should_find_the_judge_only_when_claude_is_on_path(
    judge_stub: JudgeStub, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert is_judge_available() is True
    monkeypatch.setenv("PATH", str(tmp_path / "absent"))
    assert is_judge_available() is False


def test_should_read_a_verdict_bare_or_in_one_json_fence() -> None:
    verdict_text = json.dumps(
        {
            "promised_report": True,
            "promise_span": PROMISE_SPAN,
            "decisions_as_list": False,
            "list_span": "",
        }
    )
    assert parsed_verdict(verdict_text, PROMISE_REPLY) == JudgeVerdict(PROMISE_SPAN, "")
    assert parsed_verdict(f"```json\n{verdict_text}\n```", PROMISE_REPLY) == JudgeVerdict(
        PROMISE_SPAN, ""
    )


@pytest.mark.parametrize(
    "result_text",
    [
        "The reply promises a report.",
        json.dumps(
            {
                "promised_report": True,
                "promise_span": "a report later",
                "decisions_as_list": False,
                "list_span": "",
            }
        ),
        json.dumps(
            {
                "promised_report": True,
                "promise_span": "",
                "decisions_as_list": False,
                "list_span": "",
            }
        ),
        json.dumps(
            {
                "promised_report": "yes",
                "promise_span": PROMISE_SPAN,
                "decisions_as_list": False,
                "list_span": "",
            }
        ),
        json.dumps(
            {
                "promised_report": True,
                "promise_span": PROMISE_SPAN,
                "decisions_as_list": False,
                "list_span": "",
                "note": "",
            }
        ),
    ],
)
def test_should_give_no_verdict_for_an_answer_that_is_not_the_verdict_shape(
    result_text: str,
) -> None:
    assert parsed_verdict(result_text, PROMISE_REPLY) is None


def test_should_pass_a_list_verdict_when_the_turn_used_the_question_tool() -> None:
    verdict = JudgeVerdict(PROMISE_SPAN, LIST_SPAN)
    assert gated_verdict(verdict, "Fix the build", False) == verdict
    assert gated_verdict(verdict, "Fix the build", True) == JudgeVerdict(PROMISE_SPAN, "")


def test_should_pass_a_list_verdict_when_the_prompt_asks_for_a_list() -> None:
    verdict = JudgeVerdict("", LIST_SPAN)
    assert gated_verdict(verdict, "list the open calls as bullets", False) == JudgeVerdict("", "")


def test_should_return_the_gated_verdict_from_one_child_run(judge_stub: JudgeStub) -> None:
    judge_stub.answer(
        verdict={
            "promised_report": False,
            "promise_span": "",
            "decisions_as_list": True,
            "list_span": LIST_SPAN,
        }
    )
    assert judged_verdict("Fix the build", LIST_REPLY, False) == JudgeVerdict("", LIST_SPAN)
    assert judged_verdict("list the open calls as bullets", LIST_REPLY, False) == JudgeVerdict(
        "", ""
    )
    assert len(judge_stub.calls()) == 2


def test_should_run_the_child_in_an_empty_folder_with_the_prompt_on_stdin(
    judge_stub: JudgeStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
    judged_verdict("Fix the build", PROMISE_REPLY, False)
    [child_call] = judge_stub.calls()
    assert child_call["stdin"] == judge_prompt("Fix the build", PROMISE_REPLY, False)
    assert child_call["argv"] == judge_command("claude")[1:]
    assert child_call["cwd_entries"] == []
    assert child_call["review_child"] == "1"
    assert child_call["disable_claude_mds"] == "1"
    assert child_call["disable_auto_memory"] == "1"
    assert child_call["parent_session_id"] is None


def test_should_give_no_verdict_and_log_when_the_child_times_out(
    judge_stub: JudgeStub, tmp_path: Path
) -> None:
    judge_stub.sleep(5)
    assert judged_verdict("Fix the build", PROMISE_REPLY, False, timeout_seconds=0.5) is None
    assert "the child timed out" in _log_text(tmp_path)


@pytest.mark.parametrize(
    ("set_up", "logged_reason"),
    [
        (lambda stub: stub.exit_code(1), "the child exited with code 1"),
        (lambda stub: stub.raw_stdout("not json"), "stdout is not one JSON object"),
        (lambda stub: stub.answer(result="{}", is_error=True), "the answer is marked is_error"),
        (lambda stub: stub.answer(result="no verdict here"), "the result is not the verdict shape"),
    ],
)
def test_should_give_no_verdict_and_log_when_the_child_answer_is_unusable(
    judge_stub: JudgeStub, tmp_path: Path, set_up, logged_reason: str
) -> None:
    set_up(judge_stub)
    assert judged_verdict("Fix the build", PROMISE_REPLY, False) is None
    assert logged_reason in _log_text(tmp_path)


def test_should_give_no_verdict_when_claude_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "absent"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert judged_verdict("Fix the build", PROMISE_REPLY, False) is None
    assert "the child could not start" in _log_text(tmp_path)


def test_should_write_one_log_line_per_missing_verdict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    log_no_verdict("the transcript cannot be read")
    [log_line] = _log_text(tmp_path).splitlines()
    assert log_line.endswith("closing reply judge gave no verdict: the transcript cannot be read")


def test_should_keep_a_decision_list_that_ends_the_reply_under_in_progress() -> None:
    decisions_reply = "Done.\n\nIn progress:\n- Should I delete the backup?\n- Should I merge 8590?\n- Should I close 8693?"
    assert judge_input("Fix the build", decisions_reply, False)["list_scope"] == decisions_reply
    verdict_text = json.dumps(
        {"promised_report": False, "promise_span": "", "decisions_as_list": True, "list_span": "In progress:"}
    )
    assert parsed_verdict(verdict_text, decisions_reply) == JudgeVerdict("", "In progress:")

