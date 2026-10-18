"""Refuse an efficient review on any model but haiku unless the owner named that model."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

_skill_root = Path(__file__).resolve().parents[1]
if str(_skill_root) not in sys.path:
    sys.path.insert(0, str(_skill_root))

from hooks.config.model_gate_constants import (
    HOOK_EVENT_NAME,
    REVIEW_MODEL_FAMILY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TRANSCRIPT_PATH_KEY,
)
from hooks.model_gate_command import has_unreadable_inputs, requested_model_families
from hooks.model_gate_directive import is_model_directive, newest_human_text
from tools.config.efficient_review_settings import load_settings, string_list


def block_reason_for_payload(all_payload: dict[str, object]) -> str | None:
    """Refuse unreadable inputs or any family lacking a latest-turn directive.

    Args:
        all_payload: The PreToolUse payload.

    Returns:
        The refusal text, or None when the call may proceed.
    """
    all_settings = load_settings()
    tool_name = all_payload.get(TOOL_NAME_KEY)
    all_tool_arguments = all_payload.get(TOOL_INPUT_KEY)
    if not _is_guarded(tool_name, all_settings) or not isinstance(all_tool_arguments, dict):
        return None
    if has_unreadable_inputs(tool_name, all_tool_arguments, all_settings):
        return _unreadable_reason()
    return _family_reason(all_payload, all_tool_arguments, tool_name, all_settings)


def _is_guarded(tool_name: object, all_settings: dict[str, object]) -> bool:
    allowed = {
        str(all_settings["hook_dispatch_tool"]),
        *string_list(all_settings, "hook_shell_tools"),
    }
    return tool_name in allowed


def _family_reason(
    all_payload: dict[str, object],
    all_tool_arguments: dict[str, object],
    tool_name: object,
    all_settings: dict[str, object],
) -> str | None:
    all_other_families = [
        each_family
        for each_family in requested_model_families(
            tool_name, all_tool_arguments, all_settings
        )
        if each_family != REVIEW_MODEL_FAMILY
    ]
    if not all_other_families:
        return None
    human_text = _payload_human_text(all_payload)
    return next(
        (
            _model_reason(all_settings, each_family)
            for each_family in all_other_families
            if not is_model_directive(human_text, each_family)
        ),
        None,
    )


def _payload_human_text(all_payload: dict[str, object]) -> str:
    transcript_path_text = all_payload.get(TRANSCRIPT_PATH_KEY)
    if not isinstance(transcript_path_text, str):
        return ""
    try:
        return newest_human_text(Path(transcript_path_text))
    except OSError:
        return ""


def _model_reason(all_settings: dict[str, object], family: str) -> str:
    owner = str(all_settings["owner_display_name"])
    return (
        "Efficient review runs on haiku only. "
        f"{owner}'s newest message gives no directive that names {family}, "
        f"such as 'run this review on {family}'. "
        "Leave the model input blank so the review runs on haiku, and never ask "
        "for a model. See the Defaults section of the efficient-review skill."
    )


def _unreadable_reason() -> str:
    return (
        "This efficient review takes its inputs through --json, --input, an "
        "@file field or a shell variable, so the gate cannot read the model. "
        "Pass each input as literal text with -f, such as -f model=, so the "
        "gate can confirm the review runs on haiku."
    )


def run_pretooluse_payload_guard(
    reason_for_payload: Callable[[dict[str, object]], str | None],
) -> int:
    """Read a PreToolUse payload from stdin and emit the block decision.

    Args:
        reason_for_payload: Callback receiving the payload and returning a reason.

    Returns:
        Zero always. The decision travels as stdout JSON.
    """
    raw_stdin = sys.stdin.read().strip() or "{}"
    try:
        reason = reason_for_payload(json.loads(raw_stdin))
    except (json.JSONDecodeError, AttributeError, TypeError):
        return 0
    if reason is None:
        return 0
    json.dump(_deny_payload(reason), sys.stdout)
    return 0


def _deny_payload(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main() -> int:
    """Read the hook payload from stdin and emit the decision.

    Returns:
        Zero always. The decision travels as stdout JSON.
    """
    return run_pretooluse_payload_guard(block_reason_for_payload)


if __name__ == "__main__":
    raise SystemExit(main())
