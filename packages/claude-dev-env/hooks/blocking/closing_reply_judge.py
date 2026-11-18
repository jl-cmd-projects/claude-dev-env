"""Ask one small model call whether a closing reply promises a later report or lists open decisions.

The open tasks Stop gate sends the turn's prompt and its closing reply to
``claude -p --model haiku --effort medium`` with the prompt on stdin, and reads
back one JSON verdict::

    in:  {"prompt_kind": "typed", "user_prompt": "...", "reply": "...", "question_tool_used": false,
          "list_scope": "..."}
    out: {"promised_report": true, "promise_span": "...", "decisions_as_list": false, "list_span": ""}

The prompt kind tells the model where the prompt came from::

    "<task-notification>...<summary>Lint ended</summary>..."  -> task_notification, "Lint ended"
    "<command-name>/review</command-name><command-args>12</command-args>" -> slash_command, "/review 12"
    any other prompt                                          -> typed, its first 4,000 characters

A verdict counts only when it is the four-key object, bare or in one ``json``
code fence, and each raised flag names a nonempty span found in the reply.
The list lead counts only in ``list_scope``, the reply with a status-only In
progress footer cut off by ``closing_question_round_footer.list_check_text``.
A footer that asks the user something stays in the scope. A lead in a
status-only footer,
or an ``In progress:`` lead that the body holds only inside a sentence, drops
the list flag and keeps the promise. An ``In progress:`` line in the body
over a list of decisions keeps it.
Two code gates then drop the list flag: the turn used the question tool, or
the prompt asked for a list.

The child runs in a new empty folder with no tools, no hooks, no MCP servers,
no CLAUDE.md files, no auto memory, ``CLAUDE_TURN_REVIEW_CHILD=1``, and none of
the parent session's id, messaging, or ingress variables. Every failure gives
no verdict and one line in ``~/.claude/logs/closing-reply-judge.log``::

    the child times out, cannot start, or exits with another code than 0
    stdout is not one JSON object with a string result, or is_error is set
    the result is not the verdict shape, or a span is not in the reply
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple

from closing_question_round_footer import list_check_text, split_footer
from closing_reply_shapes import prompt_asks_for_list
from hooks_constants.closing_question_round_gate_constants import FOOTER_HEADING_PATTERN
from hooks_constants.open_tasks_stop_gate_constants import OPEN_ITEM_LIST_MINIMUM
from hooks_constants.closing_reply_judge_constants import (
    ALL_JUDGE_COMMAND_FLAGS,
    ALL_JUDGE_ENVIRONMENT_SETTINGS,
    ALL_LOG_PATH_PARTS,
    ALL_VERDICT_KEYS,
    ANSWER_FENCE_PATTERN,
    ANSWER_IS_ERROR_KEY,
    ANSWER_RESULT_KEY,
    CHILD_DECODE_ERRORS,
    CHILD_TEXT_ENCODING,
    CLAUDE_EXECUTABLE_NAME,
    COMMAND_ARGS_PATTERN,
    COMMAND_NAME_PATTERN,
    COMMAND_PART_SEPARATOR,
    COMMAND_START_PATTERN,
    DECISIONS_AS_LIST_KEY,
    ERROR_ANSWER_REASON,
    EXIT_CODE_REASON_TEMPLATE,
    JUDGE_DATA_INDENT,
    JUDGE_DATA_PLACEHOLDER,
    JUDGE_PROMPT_TEMPLATE,
    JUDGE_TIMEOUT_SECONDS,
    LIST_SCOPE_KEY,
    LIST_SPAN_KEY,
    LOG_LINE_TEMPLATE,
    NO_VERDICT_LOG_TEMPLATE,
    NOT_JSON_REASON,
    NOTIFICATION_SUMMARY_PATTERN,
    PROMISE_SPAN_KEY,
    PROMISED_REPORT_KEY,
    PROMPT_KIND_KEY,
    QUESTION_TOOL_USED_KEY,
    REPLY_KEY,
    SLASH_COMMAND_PROMPT_KIND,
    START_FAILURE_REASON,
    TASK_NOTIFICATION_PREFIX,
    TASK_NOTIFICATION_PROMPT_KIND,
    TIMEOUT_REASON,
    TYPED_PROMPT_CHARACTER_LIMIT,
    TYPED_PROMPT_KIND,
    USER_PROMPT_KEY,
    VERDICT_SHAPE_REASON,
)
from hooks_constants.subprocess_window import hidden_window_creation_flags
from hooks_constants.turn_review_gate_constants import (
    ALL_PARENT_SESSION_VARIABLES,
    REVIEW_CHILD_ENVIRONMENT_VARIABLE,
    REVIEW_CHILD_MARKER,
)


class JudgeVerdict(NamedTuple):
    """The spans the judge raised: the promised report and the open-decision list, each empty when not raised."""

    promise_span: str
    list_span: str


def _log(diagnostic_text: str) -> None:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        log_path = Path.home().joinpath(*ALL_LOG_PATH_PARTS)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open(
            "a", encoding=CHILD_TEXT_ENCODING, errors=CHILD_DECODE_ERRORS
        ) as log_file:
            log_file.write(LOG_LINE_TEMPLATE.format(timestamp=timestamp, text=diagnostic_text))
    except (OSError, RuntimeError):
        return


def log_no_verdict(reason: str) -> None:
    """Write one line to the judge log that names why the judge gave no verdict."""
    _log(NO_VERDICT_LOG_TEMPLATE.format(reason=reason))


def _prompt_kind_and_text(prompt_text: str) -> tuple[str, str]:
    stripped_prompt = prompt_text.lstrip()
    if stripped_prompt.startswith(TASK_NOTIFICATION_PREFIX):
        summary_match = NOTIFICATION_SUMMARY_PATTERN.search(stripped_prompt)
        return TASK_NOTIFICATION_PROMPT_KIND, summary_match.group(
            1
        ).strip() if summary_match else ""
    if COMMAND_START_PATTERN.match(stripped_prompt):
        all_command_parts = (
            each_match.group(1).strip()
            for each_match in (
                COMMAND_NAME_PATTERN.search(stripped_prompt),
                COMMAND_ARGS_PATTERN.search(stripped_prompt),
            )
            if each_match is not None
        )
        return SLASH_COMMAND_PROMPT_KIND, COMMAND_PART_SEPARATOR.join(
            each_part for each_part in all_command_parts if each_part
        )
    return TYPED_PROMPT_KIND, prompt_text[:TYPED_PROMPT_CHARACTER_LIMIT]


def judge_input(prompt_text: str, reply_text: str, has_question_tool_call: bool) -> dict[str, object]:
    """Return the data the judge reads: the prompt kind, the prompt text, the reply, the question-tool flag, and the list scope.

    ::

        "<task-notification>...<summary>Lint ended</summary>"  -> task_notification, "Lint ended"
        "<command-name>/review</command-name>"                -> slash_command, "/review"
        "Fix the build"                                       -> typed, "Fix the build"

    Args:
        prompt_text: The prompt that started the turn.
        reply_text: The closing reply the turn ends with.
        has_question_tool_call: Whether the turn called the question tool.
    """
    prompt_kind, user_prompt = _prompt_kind_and_text(prompt_text)
    return {
        PROMPT_KIND_KEY: prompt_kind,
        USER_PROMPT_KEY: user_prompt,
        REPLY_KEY: reply_text,
        QUESTION_TOOL_USED_KEY: bool(has_question_tool_call),
        LIST_SCOPE_KEY: list_check_text(reply_text),
    }


def judge_prompt(prompt_text: str, reply_text: str, has_question_tool_call: bool) -> str:
    """Return the full judge prompt, with the ``judge_input`` data as indented JSON in place of ``$DATA``."""
    judge_data = json.dumps(
        judge_input(prompt_text, reply_text, has_question_tool_call),
        ensure_ascii=False,
        indent=JUDGE_DATA_INDENT,
    )
    return JUDGE_PROMPT_TEMPLATE.replace(JUDGE_DATA_PLACEHOLDER, judge_data)


def judge_command(claude_path: str) -> list[str]:
    """Return the ``claude -p`` command for the judge: Haiku at medium effort, JSON out, no tools, hooks, or MCP."""
    return [claude_path, *ALL_JUDGE_COMMAND_FLAGS]


def child_environment() -> dict[str, str]:
    """Return this process's environment without the parent session's variables, marked as a review child."""
    all_child_variables = {
        each_name: each_value
        for each_name, each_value in os.environ.items()
        if each_name not in ALL_PARENT_SESSION_VARIABLES
    }
    all_child_variables[REVIEW_CHILD_ENVIRONMENT_VARIABLE] = REVIEW_CHILD_MARKER
    all_child_variables.update(ALL_JUDGE_ENVIRONMENT_SETTINGS)
    return all_child_variables


def is_judge_available() -> bool:
    """Return True when a ``claude`` executable is on PATH."""
    return shutil.which(CLAUDE_EXECUTABLE_NAME) is not None


def _answer_result(stdout_text: str) -> str | None:
    try:
        answer = json.loads(stdout_text)
    except (ValueError, RecursionError):
        log_no_verdict(NOT_JSON_REASON)
        return None
    if not isinstance(answer, dict) or not isinstance(answer.get(ANSWER_RESULT_KEY), str):
        log_no_verdict(NOT_JSON_REASON)
        return None
    if answer.get(ANSWER_IS_ERROR_KEY) is True:
        log_no_verdict(ERROR_ANSWER_REASON)
        return None
    return answer[ANSWER_RESULT_KEY]


def _claude_result(claude_path: str, prompt: str, timeout_seconds: float) -> str | None:
    try:
        with tempfile.TemporaryDirectory() as empty_folder:
            completed_process = subprocess.run(
                judge_command(claude_path),
                check=False,
                capture_output=True,
                text=True,
                encoding=CHILD_TEXT_ENCODING,
                errors=CHILD_DECODE_ERRORS,
                timeout=timeout_seconds,
                cwd=empty_folder,
                env=child_environment(),
                creationflags=hidden_window_creation_flags(),
                input=prompt,
            )
    except subprocess.TimeoutExpired:
        log_no_verdict(TIMEOUT_REASON)
        return None
    except OSError:
        log_no_verdict(START_FAILURE_REASON)
        return None
    if completed_process.returncode != 0:
        log_no_verdict(EXIT_CODE_REASON_TEMPLATE.format(exit_code=completed_process.returncode))
        return None
    return _answer_result(completed_process.stdout)


def _raised_span(
    all_verdict_fields: dict[str, object], flag_key: str, span_key: str, reply_text: str
) -> str | None:
    is_raised = all_verdict_fields[flag_key]
    span = all_verdict_fields[span_key]
    if not isinstance(is_raised, bool) or not isinstance(span, str):
        return None
    if not is_raised:
        return ""
    return span if span and span in reply_text else None


def _is_heading_inside_prose(list_span: str, list_scope: str) -> bool:
    if not FOOTER_HEADING_PATTERN.fullmatch(list_span.strip()):
        return False
    return not any(FOOTER_HEADING_PATTERN.fullmatch(each_line.strip()) for each_line in list_scope.splitlines())


def _is_short_footer_list(list_span: str, list_scope: str) -> bool:
    if not FOOTER_HEADING_PATTERN.fullmatch(list_span.strip()):
        return False
    split_scope = split_footer(list_scope)
    if split_scope.footer_items is None or len(split_scope.footer_items) >= OPEN_ITEM_LIST_MINIMUM:
        return False
    return not any(FOOTER_HEADING_PATTERN.fullmatch(each_line.strip()) for each_line in split_scope.body.splitlines())


def parsed_verdict(result_text: str, reply_text: str) -> JudgeVerdict | None:
    """Return the verdict in the judge's result text, or None when it is not the verdict shape.

    ::

        '{"promised_report": true, "promise_span": "I will report back", ...}'  -> JudgeVerdict("I will report back", "")
        the same object inside one json code fence                              -> the same verdict
        a raised flag whose span is empty or not in its scope                    -> None
        a list span only in the In progress footer                               -> JudgeVerdict(<promise>, "")
        "In progress:" as the span, where the body holds it only inside prose    -> JudgeVerdict(<promise>, "")
        "In progress:" as the span, with fewer than three asks under it in scope -> JudgeVerdict(<promise>, "")
        the same, while the body holds its own "In progress:" list            -> the verdict stands
        prose, an extra key, or a string in place of a bool                      -> None

    Args:
        result_text: The ``result`` string of the ``claude -p`` JSON answer.
        reply_text: The closing reply the judge read. A list span counts only
            above its In progress footer.
    """
    fence_match = ANSWER_FENCE_PATTERN.match(result_text)
    verdict_text = fence_match.group(1) if fence_match else result_text.strip()
    try:
        all_verdict_fields = json.loads(verdict_text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(all_verdict_fields, dict) or set(all_verdict_fields) != ALL_VERDICT_KEYS:
        return None
    promise_span = _raised_span(
        all_verdict_fields, PROMISED_REPORT_KEY, PROMISE_SPAN_KEY, reply_text
    )
    list_span = _raised_span(all_verdict_fields, DECISIONS_AS_LIST_KEY, LIST_SPAN_KEY, reply_text)
    if promise_span is None or list_span is None:
        return None
    list_scope = list_check_text(reply_text)
    if (
        list_span not in list_scope
        or _is_heading_inside_prose(list_span, list_scope)
        or _is_short_footer_list(list_span, list_scope)
    ):
        return JudgeVerdict(promise_span, "")
    return JudgeVerdict(promise_span, list_span)


def gated_verdict(
    verdict: JudgeVerdict, prompt_text: str, has_question_tool_call: bool
) -> JudgeVerdict:
    """Return the verdict with its list span dropped when the turn used the question tool or the prompt asked for a list.

    ::

        list span "Open calls:", no question tool, prompt "fix the build"   -> the list span stays
        the same verdict after an AskUserQuestion call                       -> list span ""
        the same verdict after the prompt "list the open calls as bullets"   -> list span ""
    """
    if has_question_tool_call or prompt_asks_for_list(prompt_text):
        return verdict._replace(list_span="")
    return verdict


def judged_verdict(
    prompt_text: str,
    reply_text: str,
    has_question_tool_call: bool,
    timeout_seconds: float | None = None,
) -> JudgeVerdict | None:
    """Run the judge once on a closing reply and return its gated verdict, or None when it gave none.

    ::

        a reply that promises a report later   -> JudgeVerdict("<the promise>", "")
        a reply with no fault                  -> JudgeVerdict("", "")
        no claude on PATH, a timeout, a bad answer, or a span not in the reply -> None

    Args:
        prompt_text: The prompt that started the turn.
        reply_text: The closing reply the turn ends with.
        has_question_tool_call: Whether the turn called the question tool.
        timeout_seconds: How long the child may run; ``JUDGE_TIMEOUT_SECONDS`` when None.
    """
    claude_path = shutil.which(CLAUDE_EXECUTABLE_NAME)
    if claude_path is None:
        log_no_verdict(START_FAILURE_REASON)
        return None
    result_text = _claude_result(
        claude_path,
        judge_prompt(prompt_text, reply_text, has_question_tool_call),
        JUDGE_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds,
    )
    if result_text is None:
        return None
    verdict = parsed_verdict(result_text, reply_text)
    if verdict is None:
        log_no_verdict(VERDICT_SHAPE_REASON)
        return None
    return gated_verdict(verdict, prompt_text, has_question_tool_call)
