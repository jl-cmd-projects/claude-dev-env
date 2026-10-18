#!/usr/bin/env python3
"""UserPromptSubmit hook: deepen the first interactive task before work starts.

Skip checks stay local. One bounded deepen call runs only for a first task.
Claude settings and Codex cannot replace the prompt string, so this hook emits
additionalContext. Claude desktop and CLI also ship a prompt.submit mod that
rewrites the visible text; this hook stays silent when that mod is on outside
a cloud session.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_hooks_dir = str(Path(__file__).resolve().parent.parent)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)

from hooks_constants.cloud_session import is_cloud_session
from hooks_constants.deepen_first_prompt_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALL_FOUR_QUESTION_STEMS,
    QUESTION_LINE_SEPARATOR,
    ALL_HELPER_REPORT_MARKERS,
    ALL_LOOP_PROMPT_PREFIXES,
    ALL_NONINTERACTIVE_ENV_TRUE_VALUES,
    ALL_SPAWN_REWRITE_PREFIXES,
    ALL_TRIVIAL_PROMPTS,
    CLAUDE_HOST_ENV_VAR,
    CLAUDE_HOST_TRUE_VALUE,
    DEEPEN_AGENT_MARKER,
    DEEPEN_COMMAND_ENV_VAR,
    DEEPEN_COMMAND_TIMEOUT_SECONDS,
    DEEPEN_FIRST_PROMPT_PLUGIN_NAME,
    DEEPEN_MARKER,
    DEEPEN_OUTPUT_ENV_VAR,
    DEEPEN_OUTPUT_JSON,
    DEEPEN_OUTPUT_REWRITE,
    DEEPEN_REWRITE_ENV_VAR,
    DEEPEN_SLASH_COMMAND,
    DEEPEN_TURN_MARKER_SUFFIX,
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    JSONL_ROLE_KEY,
    JSONL_TYPE_KEY,
    NONINTERACTIVE_CODEX_ENV_VAR,
    NONINTERACTIVE_PRINT_ENV_VAR,
    PROMPT_FIELD_NAME,
    SESSION_ID_FIELD_NAME,
    SKIP_DEEPEN_ENV_VAR,
    SKIP_DEEPEN_TRUE_VALUE,
    TRANSCRIPT_PATH_FIELD_NAME,
    USER_PROMPT_SUBMIT_EVENT_NAME,
    USER_ROLE_NAME,
    USER_TYPE_NAME,
    UTF8_ENCODING,
)
from hooks_constants.mod_handoff import is_mod_plugin_enabled
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.subprocess_window import hidden_window_creation_flags
from deepen_role_gate import refusal_reason


class SkipReason(StrEnum):
    """Why the first-task gate left a prompt unchanged."""

    LATER_TURN = "later-turn"
    MARKER_PRESENT = "marker-present"
    SPAWN_REWRITE = "spawn-rewrite"
    SKIP_FLAG = "skip-flag"
    NONINTERACTIVE = "noninteractive"
    TRIVIAL = "trivial"
    SLASH_COMMAND = "slash-command"
    DEEPEN_AGENT = "deepen-agent"
    LOOP_OR_HELPER = "loop-or-helper"


@dataclass(frozen=True)
class Skip:
    """Leave the submitted prompt text unchanged."""

    reason: SkipReason


@dataclass(frozen=True)
class Deepen:
    """Replace the first task with a deeper rewrite."""

    rewritten_prompt: str
    additional_context: str


@dataclass(frozen=True)
class Refuse:
    """Leave the submitted prompt unchanged because the candidate rewrite failed."""

    reason: str


DeepenDecision = Skip | Deepen | Refuse


def submitted_prompt_text(all_hook_fields: dict[str, object]) -> str:
    """Return the submitted prompt text, or empty when the payload has none."""
    prompt = all_hook_fields.get(PROMPT_FIELD_NAME)
    if isinstance(prompt, str):
        return prompt
    return ""


def _env_flag_is_true(variable_name: str) -> bool:
    return os.environ.get(variable_name, "").strip().lower() in ALL_NONINTERACTIVE_ENV_TRUE_VALUES


def _normalized_prompt(prompt: str) -> str:
    return prompt.strip().lower()


def _first_token(prompt: str) -> str:
    stripped = prompt.strip()
    if not stripped:
        return ""
    return stripped.split(None, 1)[0]


def _parsed_transcript_entry(transcript_line: str) -> dict[str, object] | None:
    stripped_line = transcript_line.strip()
    if not stripped_line:
        return None
    try:
        parsed_entry = json.loads(stripped_line)
    except json.JSONDecodeError:
        return None
    return parsed_entry if isinstance(parsed_entry, dict) else None


def _is_user_entry(all_entry_fields: dict[str, object] | None) -> bool:
    if all_entry_fields is None:
        return False
    if all_entry_fields.get(JSONL_TYPE_KEY) == USER_TYPE_NAME:
        return True
    message = all_entry_fields.get("message")
    return isinstance(message, dict) and message.get(JSONL_ROLE_KEY) == USER_ROLE_NAME


def _transcript_has_prior_user_turn(transcript_path: object) -> bool:
    if not isinstance(transcript_path, str) or not transcript_path:
        return False
    try:
        with Path(transcript_path).open(encoding=UTF8_ENCODING) as transcript:
            return any(_is_user_entry(_parsed_transcript_entry(each_line)) for each_line in transcript)
    except OSError:
        return False


def _turn_marker_path(all_hook_fields: dict[str, object]) -> Path | None:
    transcript_path = all_hook_fields.get(TRANSCRIPT_PATH_FIELD_NAME)
    if isinstance(transcript_path, str) and transcript_path:
        return Path(transcript_path + DEEPEN_TURN_MARKER_SUFFIX)
    session_id = all_hook_fields.get(SESSION_ID_FIELD_NAME)
    if isinstance(session_id, str) and session_id:
        return Path(os.environ.get("TMPDIR", "/tmp")) / f"cde-deepen-{session_id}"
    return None


def _turn_marker_exists(all_hook_fields: dict[str, object]) -> bool:
    marker_path = _turn_marker_path(all_hook_fields)
    return marker_path is not None and marker_path.is_file()


def write_turn_marker(all_hook_fields: dict[str, object]) -> None:
    """Record that this session already deepened turn one."""
    marker_path = _turn_marker_path(all_hook_fields)
    if marker_path is None:
        return
    try:
        marker_path.write_text(DEEPEN_MARKER, encoding=UTF8_ENCODING)
    except OSError:
        return


def _environment_skip_reason() -> SkipReason | None:
    if os.environ.get(SKIP_DEEPEN_ENV_VAR, "").strip() == SKIP_DEEPEN_TRUE_VALUE:
        return SkipReason.SKIP_FLAG
    if _env_flag_is_true(NONINTERACTIVE_PRINT_ENV_VAR) or _env_flag_is_true(
        NONINTERACTIVE_CODEX_ENV_VAR
    ):
        return SkipReason.NONINTERACTIVE
    return None


def _marker_skip_reason(prompt: str) -> SkipReason | None:
    if DEEPEN_MARKER in prompt:
        return SkipReason.MARKER_PRESENT
    if DEEPEN_AGENT_MARKER in prompt:
        return SkipReason.DEEPEN_AGENT
    if any(prompt.startswith(each_prefix) for each_prefix in ALL_SPAWN_REWRITE_PREFIXES):
        return SkipReason.SPAWN_REWRITE
    if any(prompt.lstrip().lower().startswith(each_prefix) for each_prefix in ALL_LOOP_PROMPT_PREFIXES):
        return SkipReason.LOOP_OR_HELPER
    if any(each_marker in prompt.lower() for each_marker in ALL_HELPER_REPORT_MARKERS):
        return SkipReason.LOOP_OR_HELPER
    return None


def _shape_skip_reason(prompt: str) -> SkipReason | None:
    first_token = _first_token(prompt)
    if first_token.startswith("/") and first_token.lower() != DEEPEN_SLASH_COMMAND:
        return SkipReason.SLASH_COMMAND
    if first_token.lower() == DEEPEN_SLASH_COMMAND and prompt.strip().lower() == DEEPEN_SLASH_COMMAND:
        return SkipReason.SLASH_COMMAND
    if _normalized_prompt(prompt) in ALL_TRIVIAL_PROMPTS or not prompt.strip():
        return SkipReason.TRIVIAL
    return None


def skip_reason_for(all_hook_fields: dict[str, object]) -> SkipReason | None:
    """Return the first skip that matches, or None when the gate should deepen."""
    event_name = all_hook_fields.get("hook_event_name")
    if event_name not in (USER_PROMPT_SUBMIT_EVENT_NAME, None, ""):
        return SkipReason.LATER_TURN
    prompt = submitted_prompt_text(all_hook_fields)
    reason = _environment_skip_reason() or _marker_skip_reason(prompt) or _shape_skip_reason(prompt)
    if reason is not None:
        return reason
    if _turn_marker_exists(all_hook_fields) or _transcript_has_prior_user_turn(
        all_hook_fields.get(TRANSCRIPT_PATH_FIELD_NAME)
    ):
        return SkipReason.LATER_TURN
    return None


def task_text_for_deepen(prompt: str) -> str:
    """Return the task body, stripping a leading /deepen command when present."""
    stripped = prompt.strip()
    first_token = _first_token(stripped)
    if first_token.lower() != DEEPEN_SLASH_COMMAND:
        return stripped
    remainder = stripped[len(first_token) :].strip()
    return remainder or stripped


def _with_deepen_marker(rewritten_body: str) -> str:
    if DEEPEN_MARKER in rewritten_body:
        return rewritten_body
    return f"{DEEPEN_MARKER}\n\n{rewritten_body}"


def _command_rewrite(task_text: str) -> str | None:
    command = os.environ.get(DEEPEN_COMMAND_ENV_VAR, "").strip()
    if not command:
        return None
    try:
        completed = subprocess.run(
            shlex.split(command),
            input=task_text,
            capture_output=True,
            text=True,
            timeout=DEEPEN_COMMAND_TIMEOUT_SECONDS,
            check=False,
            creationflags=hidden_window_creation_flags(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    command_text = completed.stdout.strip()
    if completed.returncode != 0 or not command_text:
        return None
    return _with_deepen_marker(command_text)


def _default_rewrite(task_text: str) -> str:
    """Return the paste path: the four question stems and an order to do the job."""
    numbered_stems = QUESTION_LINE_SEPARATOR.join(
        f"{each_index}. {each_stem}"
        for each_index, each_stem in enumerate(ALL_FOUR_QUESTION_STEMS, start=1)
    )
    return (
        f"{DEEPEN_MARKER}\n\n"
        "Do this task as a leading practitioner in its field would.\n\n"
        f"{task_text}\n\n"
        "Cover four things the original prompt left out:\n"
        f"{numbered_stems}\n"
        "Then do exactly that job."
    )


def expand_first_task(prompt: str) -> str:
    """Rewrite a first task so the worker does the omitted expert job."""
    stub_rewrite = os.environ.get(DEEPEN_REWRITE_ENV_VAR, "").strip()
    task_text = task_text_for_deepen(prompt)
    if stub_rewrite:
        return _with_deepen_marker(stub_rewrite.replace("{prompt}", task_text))
    command_rewrite = _command_rewrite(task_text)
    if command_rewrite is not None:
        return command_rewrite
    return _default_rewrite(task_text)


def additional_context_for(rewritten_prompt: str) -> str:
    """Return the context a command hook can inject beside the original prompt."""
    return (
        f"{DEEPEN_MARKER}\n"
        "Treat the submitted prompt as this rewritten task and do only that job.\n\n"
        f"{rewritten_prompt}"
    )


def decide_first_prompt(all_hook_fields: dict[str, object]) -> DeepenDecision:
    """Skip, refuse, or deepen one UserPromptSubmit payload."""
    reason = skip_reason_for(all_hook_fields)
    if reason is not None:
        return Skip(reason)
    prompt = submitted_prompt_text(all_hook_fields)
    rewritten_prompt = expand_first_task(prompt)
    refusal = refusal_reason(task_text_for_deepen(prompt), rewritten_prompt)
    if refusal is not None:
        return Refuse(refusal)
    return Deepen(
        rewritten_prompt=rewritten_prompt,
        additional_context=additional_context_for(rewritten_prompt),
    )


def _print_skip_json(reason: SkipReason) -> None:
    sys.stdout.write(json.dumps({"decision": "skip", "reason": reason.value}) + "\n")


def _print_refuse_json(reason: str) -> None:
    sys.stdout.write(json.dumps({"decision": "refuse", "reason": reason}) + "\n")


def _print_deepen_json(deepen: Deepen) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "decision": "deepen",
                "rewrittenPrompt": deepen.rewritten_prompt,
                "additionalContext": deepen.additional_context,
            }
        )
        + "\n"
    )


def _print_additional_context(deepen: Deepen) -> None:
    sys.stdout.write(
        json.dumps(
            {
                HOOK_SPECIFIC_OUTPUT_KEY: {
                    HOOK_EVENT_NAME_KEY: USER_PROMPT_SUBMIT_EVENT_NAME,
                    ADDITIONAL_CONTEXT_KEY: deepen.additional_context,
                }
            }
        )
        + "\n"
    )


def should_leave_rewrite_to_mod() -> bool:
    """Return True when the Claude prompt.submit mod will rewrite the visible text.

    Claude Code sets ``CLAUDECODE=1`` for every command hook. Codex reads the same
    Claude settings file but runs no Claude mod, so a Codex run keeps the envelope.
    """
    is_claude_host = os.environ.get(CLAUDE_HOST_ENV_VAR, "").strip() == CLAUDE_HOST_TRUE_VALUE
    return (
        is_claude_host
        and is_mod_plugin_enabled(DEEPEN_FIRST_PROMPT_PLUGIN_NAME)
        and not is_cloud_session()
    )


def emit_decision(decision: DeepenDecision, all_hook_fields: dict[str, object]) -> None:
    """Write the host encoding for one decision."""
    output_mode = os.environ.get(DEEPEN_OUTPUT_ENV_VAR, "").strip().lower()
    if isinstance(decision, Skip):
        if output_mode == DEEPEN_OUTPUT_JSON:
            _print_skip_json(decision.reason)
        return
    if isinstance(decision, Refuse):
        if output_mode == DEEPEN_OUTPUT_JSON:
            _print_refuse_json(decision.reason)
        return
    write_turn_marker(all_hook_fields)
    if output_mode == DEEPEN_OUTPUT_JSON:
        _print_deepen_json(decision)
        return
    if output_mode == DEEPEN_OUTPUT_REWRITE:
        sys.stdout.write(decision.rewritten_prompt)
        if not decision.rewritten_prompt.endswith("\n"):
            sys.stdout.write("\n")
        return
    if should_leave_rewrite_to_mod():
        return
    _print_additional_context(decision)


def main() -> None:
    """Read one UserPromptSubmit payload and emit a skip or a deepened rewrite."""
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return
    emit_decision(decide_first_prompt(hook_payload), hook_payload)


if __name__ == "__main__":
    main()
