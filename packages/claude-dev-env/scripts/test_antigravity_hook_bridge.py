"""Tests for the Antigravity-to-Claude/Codex lifecycle hook bridge."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import antigravity_hook_bridge as bridge


def _write_script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _write_settings(root: Path, hooks: dict[str, object]) -> Path:
    settings_path = root / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    return settings_path


def test_translate_tool_call_maps_standard_antigravity_tools() -> None:
    tool_name, tool_input = bridge.translate_tool_call(
        {
            "name": "run_command",
            "args": {"CommandLine": "git status", "Cwd": "/repo"},
        }
    )
    assert tool_name == "Bash"
    assert tool_input == {"command": "git status", "cwd": "/repo"}

    tool_name, tool_input = bridge.translate_tool_call(
        {
            "name": "write_to_file",
            "args": {"TargetFile": "/repo/a.py", "CodeContent": "x = 1\n"},
        }
    )
    assert tool_name == "Write"
    assert tool_input == {"file_path": "/repo/a.py", "content": "x = 1\n"}

    tool_name, tool_input = bridge.translate_tool_call(
        {
            "name": "replace_file_content",
            "args": {
                "TargetFile": "/repo/a.py",
                "TargetContent": "old",
                "ReplacementContent": "new",
            },
        }
    )
    assert tool_name == "Edit"
    assert tool_input == {
        "file_path": "/repo/a.py",
        "old_string": "old",
        "new_string": "new",
    }

    tool_name, tool_input = bridge.translate_tool_call(
        {
            "name": "multi_replace_file_content",
            "args": {
                "TargetFile": "/repo/a.py",
                "ReplacementChunks": [
                    {"TargetContent": "a", "ReplacementContent": "b"}
                ],
            },
        }
    )
    assert tool_name == "MultiEdit"
    assert tool_input == {
        "file_path": "/repo/a.py",
        "edits": [{"old_string": "a", "new_string": "b"}],
    }

    tool_name, tool_input = bridge.translate_tool_call(
        {"name": "read_url_content", "args": {"Url": "https://example.com"}}
    )
    assert tool_name == "WebFetch"
    assert tool_input == {"url": "https://example.com"}

    tool_name, tool_input = bridge.translate_tool_call(
        {
            "name": "invoke_subagent",
            "args": {"Subagents": [{"Prompt": "Inspect repo", "Role": "Researcher"}]},
        }
    )
    assert tool_name == "Agent"
    assert tool_input["prompt"] == "Inspect repo"


def test_pre_tool_use_translates_claude_deny_and_allow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bridge, "_STATE_ROOT", tmp_path / "state")
    claude_home = tmp_path / ".claude"
    hook_script = _write_script(
        claude_home / "hooks" / "gate.py",
        (
            "import json, sys\n"
            "payload = json.load(sys.stdin)\n"
            "cmd = payload.get('tool_input', {}).get('command', '')\n"
            "if 'forbidden' in cmd:\n"
            "    print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'deny', 'permissionDecisionReason': 'blocked command'}}))\n"
        ),
    )
    _write_settings(
        claude_home,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{sys.executable}" "{hook_script}"',
                        }
                    ],
                }
            ]
        },
    )

    denied = bridge.dispatch_antigravity_event(
        "PreToolUse",
        "global",
        {
            "conversationId": "conv-1",
            "workspacePaths": [str(tmp_path)],
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "echo forbidden"},
            },
        },
        claude_home,
    )
    assert denied == {"decision": "deny", "reason": "blocked command"}

    allowed = bridge.dispatch_antigravity_event(
        "PreToolUse",
        "global",
        {
            "conversationId": "conv-1",
            "workspacePaths": [str(tmp_path)],
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "echo safe"},
            },
        },
        claude_home,
    )
    assert allowed == {"decision": "allow"}


def test_post_tool_use_buffers_advisory_for_next_pre_invocation_and_dedups_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bridge, "_STATE_ROOT", tmp_path / "state")
    claude_home = tmp_path / ".claude"
    post_hook = _write_script(
        claude_home / "hooks" / "post.py",
        (
            "import json\n"
            "print(json.dumps({'hookSpecificOutput': {'additionalContext': 'post-tool advisory'}}))\n"
        ),
    )
    prompt_hook = _write_script(
        claude_home / "hooks" / "prompt.py",
        (
            "import json, sys\n"
            "payload = json.load(sys.stdin)\n"
            "print(json.dumps({'hookSpecificOutput': {'additionalContext': 'prompt:' + payload.get('prompt', '')}}))\n"
        ),
    )
    _write_settings(
        claude_home,
        {
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{sys.executable}" "{post_hook}"',
                        }
                    ],
                }
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{sys.executable}" "{prompt_hook}"',
                        }
                    ],
                }
            ],
        },
    )

    post_outcome = bridge.dispatch_antigravity_event(
        "PostToolUse",
        "global",
        {
            "conversationId": "conv-2",
            "workspacePaths": [str(tmp_path)],
            "toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}},
        },
        claude_home,
    )
    assert post_outcome == {}

    first_pre = bridge.dispatch_antigravity_event(
        "PreInvocation",
        "global",
        {
            "conversationId": "conv-2",
            "workspacePaths": [str(tmp_path)],
            "lastUserInput": "ship it",
        },
        claude_home,
    )
    injected = first_pre["injectSteps"][0]["systemMessage"]["systemMessage"]
    assert "post-tool advisory" in injected
    assert "prompt:ship it" in injected

    second_pre = bridge.dispatch_antigravity_event(
        "PreInvocation",
        "global",
        {
            "conversationId": "conv-2",
            "workspacePaths": [str(tmp_path)],
            "lastUserInput": "ship it",
        },
        claude_home,
    )
    assert second_pre == {}


def test_session_start_and_stop_translation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bridge, "_STATE_ROOT", tmp_path / "state")
    claude_home = tmp_path / ".claude"
    start_hook = _write_script(
        claude_home / "hooks" / "start.py",
        "print('session ready')\n",
    )
    stop_hook = _write_script(
        claude_home / "hooks" / "stop.py",
        "import json\nprint(json.dumps({'decision': 'block', 'reason': 'finish tests first'}))\n",
    )
    _write_settings(
        claude_home,
        {
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{sys.executable}" "{start_hook}"',
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{sys.executable}" "{stop_hook}"',
                        }
                    ],
                }
            ],
        },
    )

    started = bridge.dispatch_antigravity_event(
        "SessionStart",
        "global",
        {"conversationId": "conv-3", "workspacePaths": [str(tmp_path)]},
        claude_home,
    )
    assert started == {
        "injectSteps": [{"systemMessage": {"systemMessage": "session ready"}}]
    }

    stop_while_busy = bridge.dispatch_antigravity_event(
        "Stop",
        "global",
        {
            "conversationId": "conv-3",
            "workspacePaths": [str(tmp_path)],
            "fullyIdle": False,
        },
        claude_home,
    )
    assert stop_while_busy == {"decision": "allow"}

    stop_when_idle = bridge.dispatch_antigravity_event(
        "Stop",
        "global",
        {
            "conversationId": "conv-3",
            "workspacePaths": [str(tmp_path)],
            "fullyIdle": True,
        },
        claude_home,
    )
    assert stop_when_idle == {
        "decision": "continue",
        "reason": "finish tests first",
    }


def test_workspace_scope_reads_repo_claude_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bridge, "_STATE_ROOT", tmp_path / "state")
    workspace = tmp_path / "repo"
    hook_script = _write_script(
        workspace / ".claude" / "hooks" / "repo_gate.py",
        (
            "import os, sys\n"
            "if os.environ.get('CLAUDE_PROJECT_DIR'):\n"
            "    sys.stderr.write('repo rule enforced')\n"
            "    raise SystemExit(2)\n"
        ),
    )
    _write_settings(
        workspace / ".claude",
        {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'"{sys.executable}" "{hook_script}"',
                        }
                    ],
                }
            ]
        },
    )

    hook_outcome = bridge.dispatch_antigravity_event(
        "PreToolUse",
        "workspace",
        {
            "conversationId": "conv-4",
            "workspacePaths": [str(workspace)],
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": str(workspace / "x.py"), "CodeContent": "1"},
            },
        },
        tmp_path / ".claude",
    )
    assert hook_outcome == {"decision": "deny", "reason": "repo rule enforced"}
