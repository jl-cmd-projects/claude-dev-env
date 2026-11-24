"""Bridge Antigravity lifecycle hooks to Claude Code and Codex command hooks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from dev_env_scripts_constants.antigravity_hook_bridge_constants import (
    ALL_ANTIGRAVITY_TO_CLAUDE_TOOLS,
    CLAUDE_CODE_REMOTE_ENV,
    CLAUDE_CONFIG_DIR_ENV,
    CLAUDE_DIRECTORY_NAME,
    CLAUDE_PROJECT_DIR_ENV,
    CONTEXT_SEPARATOR,
    DECISION_ALLOW,
    DECISION_ASK,
    DECISION_DENY,
    DEFAULT_TIMEOUT_SECONDS,
    EXIT_CODE_BLOCK,
    MAX_TIMEOUT_SECONDS,
    SCOPE_ALL,
    SCOPE_GLOBAL,
    SCOPE_WORKSPACE,
    SETTINGS_FILE_NAME,
    STATE_DIRECTORY_NAME,
)

_STATE_ROOT = Path(tempfile.gettempdir()) / STATE_DIRECTORY_NAME


def _translate_multi_replace(
    all_tool_arguments: dict[str, object],
) -> dict[str, object]:
    chunks = all_tool_arguments.get("ReplacementChunks")
    edits: list[dict[str, str]] = []
    if isinstance(chunks, list):
        for each_chunk in chunks:
            if isinstance(each_chunk, dict):
                edits.append(
                    {
                        "old_string": str(each_chunk.get("TargetContent", "")),
                        "new_string": str(each_chunk.get("ReplacementContent", "")),
                    }
                )
    return {
        "file_path": str(all_tool_arguments.get("TargetFile", "")),
        "edits": edits,
    }


def _translate_invoke_subagent(
    all_tool_arguments: dict[str, object],
) -> dict[str, object]:
    subagents = all_tool_arguments.get("Subagents")
    prompts: list[str] = []
    if isinstance(subagents, list):
        for each_spec in subagents:
            if isinstance(each_spec, dict) and each_spec.get("Prompt"):
                prompts.append(str(each_spec["Prompt"]))
    return {
        "prompt": CONTEXT_SEPARATOR.join(prompts),
        "subagents": subagents if isinstance(subagents, list) else [],
    }


def _translate_tool_arguments(
    raw_name: str, all_tool_arguments: dict[str, object]
) -> dict[str, object]:
    if raw_name == "run_command":
        translated: dict[str, object] = {
            "command": str(all_tool_arguments.get("CommandLine", "")),
        }
        if all_tool_arguments.get("Cwd"):
            translated["cwd"] = str(all_tool_arguments["Cwd"])
        return translated
    if raw_name == "write_to_file":
        return {
            "file_path": str(all_tool_arguments.get("TargetFile", "")),
            "content": str(all_tool_arguments.get("CodeContent", "")),
        }
    if raw_name == "replace_file_content":
        return {
            "file_path": str(all_tool_arguments.get("TargetFile", "")),
            "old_string": str(all_tool_arguments.get("TargetContent", "")),
            "new_string": str(all_tool_arguments.get("ReplacementContent", "")),
        }
    if raw_name == "multi_replace_file_content":
        return _translate_multi_replace(all_tool_arguments)
    if raw_name == "view_file":
        return {"file_path": str(all_tool_arguments.get("AbsolutePath", ""))}
    if raw_name == "read_url_content":
        return {"url": str(all_tool_arguments.get("Url", ""))}
    if raw_name == "invoke_subagent":
        return _translate_invoke_subagent(all_tool_arguments)
    if raw_name == "ask_question":
        return {"questions": all_tool_arguments.get("questions", [])}
    return dict(all_tool_arguments)


def translate_tool_call(
    all_tool_call_fields: dict[str, object],
) -> tuple[str, dict[str, object]]:
    """Map an Antigravity toolCall object to Claude tool_name and tool_input.

    Args:
        all_tool_call_fields: Tool call dictionary containing name and args.

    Returns:
        Tuple of translated Claude tool name and translated tool input mapping.
    """
    raw_name = str(all_tool_call_fields.get("name", ""))
    raw_arguments = all_tool_call_fields.get("args")
    all_tool_arguments: dict[str, object] = (
        raw_arguments if isinstance(raw_arguments, dict) else {}
    )
    claude_name = ALL_ANTIGRAVITY_TO_CLAUDE_TOOLS.get(raw_name, raw_name)
    return claude_name, _translate_tool_arguments(raw_name, all_tool_arguments)


def _conversation_key(conversation_id: str) -> str:
    cleaned = conversation_id or "default"
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:24]


def _advisory_buffer_path(conversation_id: str) -> Path:
    return _STATE_ROOT / f"{_conversation_key(conversation_id)}-advisories.jsonl"


def _prompt_state_path(conversation_id: str) -> Path:
    return _STATE_ROOT / f"{_conversation_key(conversation_id)}-prompt.json"


def _append_advisory(conversation_id: str, message: str) -> None:
    text = message.strip()
    if not text:
        return
    buffer_path = _advisory_buffer_path(conversation_id)
    buffer_path.parent.mkdir(parents=True, exist_ok=True)
    with buffer_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"message": text}) + "\n")


def _drain_advisories(conversation_id: str) -> list[str]:
    buffer_path = _advisory_buffer_path(conversation_id)
    if not buffer_path.is_file():
        return []
    messages: list[str] = []
    try:
        raw_lines = buffer_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    finally:
        buffer_path.unlink(missing_ok=True)
    for each_line in raw_lines:
        if not each_line.strip():
            continue
        try:
            entry = json.loads(each_line)
        except json.JSONDecodeError:
            continue
        advisory_text = entry.get("message")
        if isinstance(advisory_text, str) and advisory_text.strip():
            messages.append(advisory_text.strip())
    return messages


def _is_new_user_prompt(conversation_id: str, last_user_input: str) -> bool:
    if not last_user_input:
        return False
    digest = hashlib.sha256(last_user_input.encode("utf-8")).hexdigest()
    state_path = _prompt_state_path(conversation_id)
    previous = None
    if state_path.is_file():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8")).get("digest")
        except (OSError, json.JSONDecodeError):
            previous = None
    if previous == digest:
        return False
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"digest": digest}), encoding="utf-8")
    return True


def _matcher_matches(matcher: str, all_candidates: tuple[str, ...]) -> bool:
    if not matcher or matcher == "*":
        return True
    try:
        pattern = re.compile(matcher)
    except re.error:
        return any(matcher == each_candidate for each_candidate in all_candidates)
    return any(
        pattern.search(each_candidate) is not None for each_candidate in all_candidates
    )


def _settings_sources(
    scope: str,
    claude_home: Path,
    all_workspace_paths: list[str],
) -> list[tuple[Path, Path | None]]:
    sources: list[tuple[Path, Path | None]] = []
    if scope in (SCOPE_GLOBAL, SCOPE_ALL):
        global_settings = claude_home / SETTINGS_FILE_NAME
        if global_settings.is_file():
            sources.append((global_settings, None))
    if scope in (SCOPE_WORKSPACE, SCOPE_ALL):
        seen: set[Path] = set()
        for each_workspace in all_workspace_paths:
            workspace_dir = Path(each_workspace).resolve()
            if workspace_dir in seen:
                continue
            seen.add(workspace_dir)
            workspace_settings = (
                workspace_dir / CLAUDE_DIRECTORY_NAME / SETTINGS_FILE_NAME
            )
            if workspace_settings.is_file():
                sources.append((workspace_settings, workspace_dir))
    return sources


def _collect_commands(
    settings_path: Path,
    claude_event: str,
    all_match_candidates: tuple[str, ...],
) -> list[tuple[str, int]]:
    try:
        settings_payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    hooks_section = settings_payload.get("hooks")
    if not isinstance(hooks_section, dict):
        return []
    groups = hooks_section.get(claude_event)
    if not isinstance(groups, list):
        return []
    commands: list[tuple[str, int]] = []
    for each_group in groups:
        if not isinstance(each_group, dict):
            continue
        matcher = str(each_group.get("matcher", ""))
        if claude_event == "SessionStart" and matcher == "compact":
            continue
        if claude_event in (
            "PreToolUse",
            "PostToolUse",
            "PostToolUseFailure",
        ) and not _matcher_matches(matcher, all_match_candidates):
            continue
        group_hooks = each_group.get("hooks")
        if not isinstance(group_hooks, list):
            continue
        for each_hook in group_hooks:
            if not isinstance(each_hook, dict):
                continue
            if each_hook.get("type", "command") != "command":
                continue
            hook_command = each_hook.get("command")
            if not isinstance(hook_command, str) or not hook_command.strip():
                continue
            raw_timeout = each_hook.get("timeout")
            timeout_seconds = (
                int(raw_timeout)
                if isinstance(raw_timeout, (int, float)) and raw_timeout > 0
                else DEFAULT_TIMEOUT_SECONDS
            )
            commands.append((hook_command, min(timeout_seconds, MAX_TIMEOUT_SECONDS)))
    return commands


def _parse_hook_verdict(stdout: str, stderr: str, returncode: int) -> dict[str, str]:
    parsed: dict[str, object] | None = None
    stripped = stdout.strip()
    if stripped.startswith("{"):
        try:
            candidate = json.loads(stripped)
            if isinstance(candidate, dict):
                parsed = candidate
        except json.JSONDecodeError:
            parsed = None

    decision = DECISION_ALLOW
    reason = ""
    context_parts: list[str] = []

    if parsed is not None:
        specific = parsed.get("hookSpecificOutput")
        if isinstance(specific, dict):
            permission_decision = specific.get("permissionDecision")
            if permission_decision in (DECISION_DENY, DECISION_ASK):
                decision = str(permission_decision)
                reason = str(specific.get("permissionDecisionReason") or "")
            extra_context = specific.get("additionalContext")
            if isinstance(extra_context, str) and extra_context.strip():
                context_parts.append(extra_context.strip())
        if parsed.get("decision") == "block":
            decision = DECISION_DENY
            reason = str(parsed.get("reason") or reason)
        system_message = parsed.get("systemMessage")
        if isinstance(system_message, str) and system_message.strip():
            context_parts.append(system_message.strip())
    elif stripped:
        context_parts.append(stripped)

    if returncode == EXIT_CODE_BLOCK and decision == DECISION_ALLOW:
        decision = DECISION_DENY
        reason = stderr.strip() or stripped or "Blocked by hook"

    return {
        "decision": decision,
        "reason": reason,
        "context": CONTEXT_SEPARATOR.join(context_parts),
    }


def _run_hook_command(
    command: str,
    timeout_seconds: int,
    all_stdin_fields: dict[str, object],
    project_dir: Path | None,
    cwd: str | None,
) -> dict[str, str]:
    process_env = os.environ.copy()
    process_env.setdefault(CLAUDE_CODE_REMOTE_ENV, "true")
    if project_dir is not None:
        process_env[CLAUDE_PROJECT_DIR_ENV] = str(project_dir)
    run_cwd = str(project_dir) if project_dir is not None else (cwd or None)
    try:
        completed = subprocess.run(
            ["bash", "-c", command],
            input=json.dumps(all_stdin_fields),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=process_env,
            cwd=run_cwd,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"decision": DECISION_ALLOW, "reason": "", "context": ""}
    return _parse_hook_verdict(completed.stdout, completed.stderr, completed.returncode)


def _base_claude_payload(
    all_payload_fields: dict[str, object],
    claude_event: str,
    cwd: str,
) -> dict[str, object]:
    return {
        "session_id": str(all_payload_fields.get("conversationId", "")),
        "transcript_path": str(all_payload_fields.get("transcriptPath", "")),
        "cwd": cwd,
        "hook_event_name": claude_event,
    }


def _inject_system_message(all_contexts: list[str]) -> dict[str, object]:
    if not all_contexts:
        return {}
    return {
        "injectSteps": [
            {"systemMessage": {"systemMessage": CONTEXT_SEPARATOR.join(all_contexts)}}
        ]
    }


def _dispatch_session_start(
    all_payload_fields: dict[str, object],
    all_sources: list[tuple[Path, Path | None]],
    default_cwd: str,
) -> dict[str, object]:
    contexts: list[str] = []
    claude_payload = _base_claude_payload(
        all_payload_fields, "SessionStart", default_cwd
    )
    claude_payload["source"] = "startup"
    for each_settings_path, each_project_dir in all_sources:
        for each_command, each_timeout in _collect_commands(
            each_settings_path, "SessionStart", ()
        ):
            if "session-start.sh" in each_command:
                continue
            outcome = _run_hook_command(
                each_command,
                each_timeout,
                claude_payload,
                each_project_dir,
                default_cwd,
            )
            if outcome["context"]:
                contexts.append(outcome["context"])
    return _inject_system_message(contexts)


def _dispatch_pre_invocation(
    all_payload_fields: dict[str, object],
    all_sources: list[tuple[Path, Path | None]],
    conversation_id: str,
    default_cwd: str,
) -> dict[str, object]:
    contexts = _drain_advisories(conversation_id)
    last_user_input = str(all_payload_fields.get("lastUserInput", ""))
    if _is_new_user_prompt(conversation_id, last_user_input):
        claude_payload = _base_claude_payload(
            all_payload_fields, "UserPromptSubmit", default_cwd
        )
        claude_payload["prompt"] = last_user_input
        for each_settings_path, each_project_dir in all_sources:
            for each_command, each_timeout in _collect_commands(
                each_settings_path, "UserPromptSubmit", ()
            ):
                outcome = _run_hook_command(
                    each_command,
                    each_timeout,
                    claude_payload,
                    each_project_dir,
                    default_cwd,
                )
                if outcome["decision"] == "deny":
                    return {
                        "injectSteps": [
                            {
                                "errorMessage": {
                                    "userMessage": outcome["reason"]
                                    or "Prompt blocked by hook."
                                }
                            }
                        ],
                        "terminationBehavior": "terminate",
                    }
                if outcome["context"]:
                    contexts.append(outcome["context"])
    return _inject_system_message(contexts)


def _dispatch_pre_tool_use(
    all_payload_fields: dict[str, object],
    all_sources: list[tuple[Path, Path | None]],
    conversation_id: str,
    default_cwd: str,
) -> dict[str, object]:
    raw_tool_call = all_payload_fields.get("toolCall")
    tool_call_dict = raw_tool_call if isinstance(raw_tool_call, dict) else {}
    raw_name = str(tool_call_dict.get("name", ""))
    claude_name, tool_input = translate_tool_call(tool_call_dict)
    tool_cwd = str(tool_input.get("cwd") or default_cwd)
    claude_payload = _base_claude_payload(all_payload_fields, "PreToolUse", tool_cwd)
    claude_payload["tool_name"] = claude_name
    claude_payload["tool_input"] = tool_input
    candidates = (claude_name, raw_name) if raw_name != claude_name else (claude_name,)
    ask_reason = ""
    for each_settings_path, each_project_dir in all_sources:
        for each_command, each_timeout in _collect_commands(
            each_settings_path, "PreToolUse", candidates
        ):
            outcome = _run_hook_command(
                each_command,
                each_timeout,
                claude_payload,
                each_project_dir,
                tool_cwd,
            )
            if outcome["decision"] == "deny":
                return {
                    "decision": "deny",
                    "reason": outcome["reason"] or "Blocked by hook.",
                }
            if outcome["decision"] == "ask" and not ask_reason:
                ask_reason = outcome["reason"] or "Confirmation required by hook."
            if outcome["context"]:
                _append_advisory(conversation_id, outcome["context"])
    if ask_reason:
        return {"decision": "ask", "reason": ask_reason}
    return {"decision": "allow"}


def _dispatch_post_tool_use(
    all_payload_fields: dict[str, object],
    all_sources: list[tuple[Path, Path | None]],
    conversation_id: str,
    default_cwd: str,
) -> dict[str, object]:
    raw_tool_call = all_payload_fields.get("toolCall")
    tool_call_dict = raw_tool_call if isinstance(raw_tool_call, dict) else {}
    raw_name = str(tool_call_dict.get("name", ""))
    claude_name, tool_input = translate_tool_call(tool_call_dict)
    tool_cwd = str(tool_input.get("cwd") or default_cwd)
    error_text = str(all_payload_fields.get("error", ""))
    claude_event = "PostToolUseFailure" if error_text else "PostToolUse"
    claude_payload = _base_claude_payload(all_payload_fields, claude_event, tool_cwd)
    claude_payload["tool_name"] = claude_name
    claude_payload["tool_input"] = tool_input
    if error_text:
        claude_payload["error"] = error_text
    candidates = (claude_name, raw_name) if raw_name != claude_name else (claude_name,)
    for each_settings_path, each_project_dir in all_sources:
        for each_command, each_timeout in _collect_commands(
            each_settings_path, claude_event, candidates
        ):
            outcome = _run_hook_command(
                each_command,
                each_timeout,
                claude_payload,
                each_project_dir,
                tool_cwd,
            )
            if outcome["context"]:
                _append_advisory(conversation_id, outcome["context"])
            if outcome["decision"] == "deny" and outcome["reason"]:
                _append_advisory(conversation_id, outcome["reason"])
    return {}


def _dispatch_stop(
    all_payload_fields: dict[str, object],
    all_sources: list[tuple[Path, Path | None]],
    default_cwd: str,
) -> dict[str, object]:
    if all_payload_fields.get("fullyIdle") is False:
        return {"decision": "allow"}
    claude_payload = _base_claude_payload(all_payload_fields, "Stop", default_cwd)
    execution_num = all_payload_fields.get("executionNum", 0)
    claude_payload["stop_hook_active"] = bool(
        isinstance(execution_num, int) and execution_num > 1
    )
    for each_settings_path, each_project_dir in all_sources:
        for each_command, each_timeout in _collect_commands(
            each_settings_path, "Stop", ()
        ):
            outcome = _run_hook_command(
                each_command,
                each_timeout,
                claude_payload,
                each_project_dir,
                default_cwd,
            )
            if outcome["decision"] == "deny":
                return {
                    "decision": "continue",
                    "reason": outcome["reason"] or "Stop blocked by hook.",
                }
    return {"decision": "allow"}


def dispatch_antigravity_event(
    event: str,
    scope: str,
    all_payload_fields: dict[str, object],
    claude_home: Path,
) -> dict[str, object]:
    """Dispatch one Antigravity hook event to matching Claude/Codex hooks.

    Args:
        event: Antigravity lifecycle event name.
        scope: Hook source scope (global, workspace, or all).
        all_payload_fields: Parsed JSON object received on stdin.
        claude_home: Path to the Claude configuration directory.

    Returns:
        Antigravity-formatted JSON response dictionary for stdout.
    """
    conversation_id = str(all_payload_fields.get("conversationId", ""))
    raw_workspaces = all_payload_fields.get("workspacePaths")
    workspace_paths = (
        [
            str(each_workspace_entry)
            for each_workspace_entry in raw_workspaces
            if isinstance(each_workspace_entry, str) and each_workspace_entry
        ]
        if isinstance(raw_workspaces, list)
        else []
    )
    default_cwd = workspace_paths[0] if workspace_paths else os.getcwd()
    all_sources = _settings_sources(scope, claude_home, workspace_paths)

    if event == "SessionStart":
        return _dispatch_session_start(all_payload_fields, all_sources, default_cwd)
    if event == "PreInvocation":
        return _dispatch_pre_invocation(
            all_payload_fields, all_sources, conversation_id, default_cwd
        )
    if event == "PreToolUse":
        return _dispatch_pre_tool_use(
            all_payload_fields, all_sources, conversation_id, default_cwd
        )
    if event == "PostToolUse":
        return _dispatch_post_tool_use(
            all_payload_fields, all_sources, conversation_id, default_cwd
        )
    if event == "Stop":
        return _dispatch_stop(all_payload_fields, all_sources, default_cwd)
    return {}


def main() -> int:
    """Read Antigravity hook JSON from stdin and write the hook decision JSON.

    Args:
        None. Reads command-line flags from sys.argv and JSON from sys.stdin.

    Returns:
        Process exit status code (0 on completion).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event",
        required=True,
        choices=(
            "SessionStart",
            "PreInvocation",
            "PreToolUse",
            "PostToolUse",
            "PostInvocation",
            "Stop",
        ),
    )
    parser.add_argument(
        "--scope",
        default=SCOPE_GLOBAL,
        choices=(SCOPE_GLOBAL, SCOPE_WORKSPACE, SCOPE_ALL),
    )
    parser.add_argument(
        "--claude-home",
        type=Path,
        default=Path(
            os.environ.get(CLAUDE_CONFIG_DIR_ENV)
            or (Path.home() / CLAUDE_DIRECTORY_NAME)
        ),
    )
    parsed_arguments = parser.parse_args()
    raw_stdin = sys.stdin.read()
    try:
        payload = json.loads(raw_stdin) if raw_stdin.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    bridge_verdict = dispatch_antigravity_event(
        parsed_arguments.event,
        parsed_arguments.scope,
        payload,
        parsed_arguments.claude_home,
    )
    sys.stdout.write(json.dumps(bridge_verdict) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
