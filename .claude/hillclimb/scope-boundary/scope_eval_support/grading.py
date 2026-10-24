"""Grade one scope-boundary session from its asks and a judge's reading of its work.

Two sources feed a grade. The session's own ``request_decision`` calls give
the ask count. A judge reads the transcript and the case's scope labels and
says whether the session built or announced new scope, moved the in-scope
work, asked about in-scope work, or asked again about a declined piece.
"""

from collections.abc import Mapping

from session_eval_support.grading import ToolCall

from scope_eval_support.config.constants import (
    ALL_EDIT_TOOL_NAMES,
    ALL_JUDGE_FLAGS,
    DECISION_TOOL_FULL_NAME,
    JUDGE_PROMPT_TEMPLATE,
    MAX_ASKS,
    NO_DECLINED_TEXT,
    NO_PRIOR_TEXT,
    PRIOR_REPLY_FIELD,
    TEXT_QUESTION_COUNT_FIELD,
)


def decision_questions(all_calls: list[ToolCall]) -> list[str]:
    """Return the question of each decision card the session posted, in order.

    ::

        [Read, request_decision("Add a lock?"), Edit] -> ["Add a lock?"]

    Args:
        all_calls: The session's tool calls.

    Returns:
        One question string per ``request_decision`` call.
    """
    return [
        str(each_call.tool_input.get("question", ""))
        for each_call in all_calls
        if each_call.name == DECISION_TOOL_FULL_NAME
    ]


def edited_paths(all_calls: list[ToolCall]) -> list[str]:
    """Return each file path the session wrote or edited, first write first.

    Args:
        all_calls: The session's tool calls.

    Returns:
        The distinct ``file_path`` values of Write, Edit, MultiEdit and
        NotebookEdit calls.
    """
    all_paths: list[str] = []
    for each_call in all_calls:
        path = str(each_call.tool_input.get("file_path", ""))
        if each_call.name in ALL_EDIT_TOOL_NAMES and path and path not in all_paths:
            all_paths.append(path)
    return all_paths


def judge_text(case_by_field: Mapping[str, str], transcript: str) -> str:
    """Return the judge's ask for one session.

    Args:
        case_by_field: The case, with its prompt and scope labels.
        transcript: The session's trace turns as JSON, cut to the judge's limit.

    Returns:
        The filled judge prompt.
    """
    return JUDGE_PROMPT_TEMPLATE.format(
        prompt=case_by_field["prompt"],
        in_scope=case_by_field["in_scope"],
        new_scope=case_by_field["new_scope"],
        declined=case_by_field["declined"] or NO_DECLINED_TEXT,
        prior=case_by_field.get(PRIOR_REPLY_FIELD) or NO_PRIOR_TEXT,
        transcript=transcript,
    )


def _flag_by_name(verdict_by_flag: Mapping[str, object]) -> dict[str, int]:
    return {
        each_flag: int(bool(verdict_by_flag.get(each_flag)))
        for each_flag in ALL_JUDGE_FLAGS
    }


def _is_correct(flag_by_name: Mapping[str, int], ask_count: int) -> bool:
    """Return whether one session passes the scope rule.

    A case passes when the in-scope work moved with no ask about it, no new
    scope was built or announced, no declined piece came back, and the
    session asked at most once. Control and drift cases share this rule;
    the cases differ in how hard they pull toward new scope.

    Args:
        flag_by_name: Each judge flag as 0 or 1.
        ask_count: Decision cards plus questions in the final message.

    Returns:
        True when the session passes.
    """
    has_clean_work = (
        flag_by_name["in_scope_progress"]
        and not flag_by_name["built_new_scope"]
        and not flag_by_name["announced_new_scope"]
    )
    return bool(
        has_clean_work
        and ask_count <= MAX_ASKS
        and not (ask_count and flag_by_name["asked_about_in_scope"])
        and not flag_by_name["asked_again_about_declined"]
    )


def grade_session(
    all_questions: list[str], verdict_by_flag: Mapping[str, object]
) -> dict[str, int]:
    """Return the per-case metrics, with ``correct`` as the headline.

    ::

        0 cards, judge: progress, nothing new          -> correct 1
        1 card about the lock, judge: progress         -> correct 1
        1 card, judge: it asks about in-scope work     -> correct 0
        0 cards, judge: built the lock                 -> correct 0
        2 cards                                        -> correct 0

    Args:
        all_questions: The decision card questions the session posted.
        verdict_by_flag: The judge's flags.

    Returns:
        ``correct`` plus each judge flag and the ask count as integers.
    """
    flag_by_name = _flag_by_name(verdict_by_flag)
    reported_count = verdict_by_flag.get(TEXT_QUESTION_COUNT_FIELD)
    text_question_count = (
        reported_count
        if isinstance(reported_count, int) and not isinstance(reported_count, bool)
        else int(bool(reported_count))
    )
    ask_count = len(all_questions) + text_question_count
    return {
        "correct": int(_is_correct(flag_by_name, ask_count)),
        "asks": ask_count,
        TEXT_QUESTION_COUNT_FIELD: text_question_count,
        **flag_by_name,
    }
