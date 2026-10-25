#!/usr/bin/env python3
"""PreToolUse gate: deny a recursive walk or content search over a Claude transcript root.

A transcript root is a ``projects`` folder directly under ``.claude``, under
``.claude-<name>``, or under ``.claude-profiles/<profile>``. It holds one
folder per project and thousands of JSONL session transcripts, so a walk that
starts there reads every transcript and runs for minutes. The gate denies a
search start that names a transcript root with no project folder after it,
when the search recurses, and a start whose first segment after the root is
a bare wildcard such as ``*`` or ``**`` that descends into every project
folder. A name-filtered listing of the root, such as ``Get-ChildItem <root>
-Directory -Filter "*id*"`` or ``Glob(pattern="*id*", path=<root>)``, passes,
and so does any walk inside one project folder.

::

    Get-ChildItem $p -Recurse -Filter *.jsonl      flag  ($p bound to a root earlier in the command)
    Get-ChildItem $p -Directory -Filter "*01WU*"   ok    (one-level name listing)
    grep needle ~/.claude/projects/*/*.jsonl       flag  (bare wildcard over every folder)
    Grep(path="~/.claude/projects")                flag  (Grep always recurses)

Shell variables assigned in the same command, such as ``$p="..."`` or
``p=...``, are expanded before the path is read. The Bash and PowerShell
tools reach the gate through ``blocking/bash_pre_tool_use_dispatcher.py``;
``hooks.json`` registers it directly for the Grep and Glob tools.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    _hooks_root_directory = str(Path(__file__).resolve().parent.parent)
    if _hooks_root_directory not in sys.path:
        sys.path.insert(0, _hooks_root_directory)
    from hooks_constants import transcript_root_search_gate_constants as search_rules
    from hooks_constants.bash_pre_tool_use_dispatcher_constants import (
        ALL_BASH_AND_POWERSHELL_TOOL_NAMES,
        DENY_DECISION,
        HOOK_EVENT_NAME,
    )
    from hooks_constants.hook_block_logger import log_hook_block
    from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin
    from blocking.transcript_root_search_starts import (
        SearchStart,
        file_search_tool_start,
        walked_transcript_root,
    )
    from blocking.transcript_root_shell_starts import shell_command_search_starts
except ImportError as import_error:
    raise ImportError(
        "The transcript root search gate cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _call_search_starts(
    tool_name: str, all_tool_input: dict[str, object], cwd: str
) -> list[SearchStart]:
    if tool_name in ALL_BASH_AND_POWERSHELL_TOOL_NAMES:
        command = all_tool_input.get(search_rules.TOOL_INPUT_COMMAND_KEY)
        if not isinstance(command, str):
            return []
        return shell_command_search_starts(
            command, cwd, tool_name == search_rules.POWERSHELL_TOOL_NAME
        )
    if tool_name in search_rules.ALL_FILE_SEARCH_TOOL_NAMES:
        return [file_search_tool_start(tool_name, all_tool_input, cwd)]
    return []


def transcript_root_decision(all_hook_payload: dict[str, object]) -> dict[str, object] | None:
    """Return the deny decision for a search that walks a transcript root, else None.

    Args:
        all_hook_payload: The PreToolUse payload the hook read from stdin.
    """
    tool_name = all_hook_payload.get(search_rules.PAYLOAD_TOOL_NAME_KEY)
    all_tool_input = all_hook_payload.get(search_rules.PAYLOAD_TOOL_INPUT_KEY)
    raw_cwd = all_hook_payload.get(search_rules.PAYLOAD_CWD_KEY)
    if not isinstance(tool_name, str) or not isinstance(all_tool_input, dict):
        return None
    cwd = raw_cwd if isinstance(raw_cwd, str) else ""
    all_walked_roots = (
        walked_transcript_root(each_start)
        for each_start in _call_search_starts(tool_name, all_tool_input, cwd)
    )
    transcript_root = next((each_root for each_root in all_walked_roots if each_root), None)
    if transcript_root is None:
        return None
    deny_reason = search_rules.TRANSCRIPT_ROOT_DENY_REASON_TEMPLATE.format(root=transcript_root)
    log_hook_block(
        search_rules.GATE_HOOK_NAME,
        HOOK_EVENT_NAME,
        deny_reason,
        tool_name,
        json.dumps(all_tool_input),
    )
    return _deny_decision(deny_reason)


def _deny_decision(deny_reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "permissionDecision": DENY_DECISION,
            "permissionDecisionReason": deny_reason,
        }
    }


def main() -> None:
    """Deny a search that walks a Claude transcript root, or stay quiet."""
    print_decision_from_stdin(transcript_root_decision)


if __name__ == "__main__":
    main()
