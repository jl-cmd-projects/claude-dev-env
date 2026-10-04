import json

from hooks_constants.spawn_readiness_hook_constants import MISSING_INVESTIGATION_REASON
from spawn_readiness_steps import SessionStep, readiness_gaps, session_steps


def _user(text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _tool_use(name: str, tool_input: dict[str, object], block_id: str = "toolu_x") -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": block_id, "name": name, "input": tool_input}],
        },
    }


def _tool_result(tool_use_id: str) -> dict[str, object]:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}],
        },
    }


READ_STEP = _tool_use("Bash", {"command": "cat README.md"})


def test_should_skip_meta_entries_and_tool_results_as_user_messages() -> None:
    all_lines = [
        json.dumps(_user("Build the hook.")),
        json.dumps({**_user("Base directory for this skill"), "isMeta": True}),
        json.dumps(READ_STEP),
        json.dumps(_tool_result("toolu_x")),
    ]
    assert session_steps(all_lines) == [
        SessionStep.USER_MESSAGE,
        SessionStep.READ,
    ]


def test_should_leave_the_spawn_under_check_out_of_the_steps() -> None:
    explore = _tool_use(
        "Agent", {"subagent_type": "Explore", "prompt": "Find it."}, block_id="toolu_spawn"
    )
    all_lines = [json.dumps(_user("Build the hook.")), json.dumps(explore)]
    assert session_steps(all_lines, "toolu_spawn") == [
        SessionStep.USER_MESSAGE
    ]


def test_should_report_no_gaps_for_a_reply_after_a_question() -> None:
    all_steps = [
        SessionStep.USER_MESSAGE,
        SessionStep.READ,
        SessionStep.QUESTION,
        SessionStep.USER_MESSAGE,
    ]
    assert readiness_gaps(all_steps) == []


def test_should_read_a_github_get_call_as_a_read_and_a_chat_question_as_another_call() -> None:
    all_lines = [
        json.dumps(_tool_use("mcp__github__get_file_contents", {"path": "a"})),
        json.dumps(_tool_use("mcp__hearthbot__reply", {"text": "Which one?"})),
        json.dumps(_tool_use("mcp__hearthbot__ask_decision", {"question": "Which one?"})),
    ]
    assert session_steps(all_lines) == [SessionStep.READ, SessionStep.OTHER_TOOL_CALL, SessionStep.QUESTION]


def test_should_start_the_span_at_the_request_before_an_answered_question() -> None:
    all_steps = [
        SessionStep.USER_MESSAGE,
        SessionStep.READ,
        SessionStep.OTHER_TOOL_CALL,
        SessionStep.USER_MESSAGE,
        SessionStep.QUESTION,
        SessionStep.USER_MESSAGE,
    ]
    assert readiness_gaps(all_steps) == [MISSING_INVESTIGATION_REASON]
