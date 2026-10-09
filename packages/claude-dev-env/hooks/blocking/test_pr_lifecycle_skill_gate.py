"""Behavior tests for the pull request lifecycle PreToolUse gate."""

import json
import subprocess
import sys
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from unittest.mock import patch

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import followup_pr_dedupe as gate_dedupe
from blocking import pr_lifecycle_skill_gate as gate
from hooks_constants.pr_lifecycle_skill_gate_constants import DENY_REASON
from hooks_constants.pull_request_proof_constants import MISSING_BUILD_EVAL_REASON, MISSING_PROOF_REASON

PROVEN_FOLLOWUP_BODY = (
    "Follow-up to #1731\n\n## Existing work\nNothing found in open or merged pull requests.\n\n"
    "## Proof in practice\nRan `python probe.py`.\n"
)


def _transcript(tmp_path: Path, skill_name: str | None = None, compact: bool = False) -> Path:
    lines = [json.dumps({"type": "user", "message": {"content": "Start."}})]
    if skill_name:
        lines.append(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": skill_name}}]}}))
    if compact:
        lines.append(json.dumps({"subtype": "compact_boundary"}))
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return transcript_path


def _payload(command: str, path: Path, tool_name: str = "Bash") -> dict[str, object]:
    return {"tool_name": tool_name, "tool_input": {"command": command}, "transcript_path": str(path)}


def _run_main(payload: object) -> tuple[int, str]:
    stdin_text = payload if isinstance(payload, str) else json.dumps(payload)
    output = StringIO()
    input_stream = TextIOWrapper(BytesIO(stdin_text.encode("utf-8")), encoding="utf-8")
    with patch("sys.stdin", input_stream), patch("sys.stdout", output):
        exit_code = gate.main()
    return exit_code, output.getvalue()


def _assert_denied(payload: dict[str, object]) -> None:
    assert gate.decision_for(payload) == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": DENY_REASON,
        }
    }


def test_unloaded_pull_request_command_is_denied(tmp_path: Path) -> None:
    exit_code, output = _run_main(_payload("gh pr create", _transcript(tmp_path)))
    assert exit_code == 0
    decision = json.loads(output)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "Skill tool" in decision["permissionDecisionReason"]
    assert "same command again" in decision["permissionDecisionReason"]


def test_loaded_skill_allows_action_silently(tmp_path: Path) -> None:
    path = _transcript(tmp_path, "plugin:pr-lifecycle")
    assert _run_main(_payload("gh pr view", path)) == (0, "")


def test_user_slash_command_loads_skill(tmp_path: Path) -> None:
    path = tmp_path / "slash.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"content": "<command-name>/pr-lifecycle</command-name>"}}) + "\n", encoding="utf-8")
    assert _run_main(_payload("git commit", path)) == (0, "")


def test_compaction_requires_another_invocation(tmp_path: Path) -> None:
    _assert_denied(_payload("git push", _transcript(tmp_path, "pr-lifecycle", compact=True)))


def test_agent_transcript_can_supply_invocation(tmp_path: Path) -> None:
    session_path = _transcript(tmp_path)
    agent_path = tmp_path / "agent.jsonl"
    agent_path.write_text(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "pr-lifecycle"}}]}}) + "\n", encoding="utf-8")
    payload = _payload("git push", session_path)
    payload["agent_transcript_path"] = str(agent_path)
    assert gate.decision_for(payload) is None


def _subagent_transcript(tmp_path: Path, agent_id: str, skill_name: str | None) -> Path:
    subagent_directory = tmp_path / "session" / "subagents"
    subagent_directory.mkdir(parents=True)
    subagent_path = subagent_directory / f"agent-{agent_id}.jsonl"
    lines = [json.dumps({"type": "user", "message": {"content": "Task."}})]
    if skill_name:
        lines.append(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": skill_name}}]}}))
    subagent_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return subagent_path


def test_subagent_transcript_located_by_agent_id_can_supply_invocation(tmp_path: Path) -> None:
    session_path = _transcript(tmp_path)
    _subagent_transcript(tmp_path, "a8865a3f3c71595ce", "pr-lifecycle")
    payload = _payload("git commit", session_path)
    payload["agent_id"] = "a8865a3f3c71595ce"
    assert _run_main(payload) == (0, "")


def test_subagent_without_invocation_is_denied(tmp_path: Path) -> None:
    session_path = _transcript(tmp_path)
    _subagent_transcript(tmp_path, "a8865a3f3c71595ce", None)
    payload = _payload("git push", session_path)
    payload["agent_id"] = "a8865a3f3c71595ce"
    _assert_denied(payload)


def test_missing_subagent_transcript_keeps_session_deny(tmp_path: Path) -> None:
    payload = _payload("git push", _transcript(tmp_path))
    payload["agent_id"] = "a8865a3f3c71595ce"
    _assert_denied(payload)


def test_agent_id_with_path_separator_is_not_followed(tmp_path: Path) -> None:
    session_path = _transcript(tmp_path)
    escaped_path = tmp_path / "session" / "agent-x.jsonl"
    escaped_path.parent.mkdir(parents=True)
    escaped_path.write_text(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "pr-lifecycle"}}]}}) + "\n", encoding="utf-8")
    payload = _payload("git push", session_path)
    payload["agent_id"] = "../agent-x"
    _assert_denied(payload)


def test_unreadable_or_missing_transcript_allows_silently(tmp_path: Path) -> None:
    payload = _payload("gh pr view", tmp_path / "missing.jsonl")
    assert _run_main(payload) == (0, "")
    payload.pop("transcript_path")
    assert _run_main(payload) == (0, "")


def test_action_command_shapes(tmp_path: Path) -> None:
    path = _transcript(tmp_path)
    commands = (
        "git commit",
        "git -C some/path commit -F message.txt",
        "git --git-dir=.git push origin head",
        "gh pr create",
        "gh -R owner/repo pr --repo owner/repo merge",
        "gh api -X PUT repos/owner/repo/pulls/1/merge",
        "gh api graphql -f query='mutation { enablePullRequestAutoMerge }'",
        "gh api graphql -f name=auto-merge",
        "echo done; gh pr edit",
        "GIT_TRACE=1 git push",
        "env -u GH_TOKEN gh pr merge 1",
        "env --unset=GH_TOKEN GH_HOST=github.com gh pr create",
        "sudo git push",
        "(git push)",
    )
    for command in commands:
        _assert_denied(_payload(command, path, "PowerShell"))


def test_non_action_command_shapes(tmp_path: Path) -> None:
    path = _transcript(tmp_path)
    commands = (
        "git status",
        "git commit-tree 123",
        "git log --grep push",
        "echo 'gh pr create'",
        "gh api repos/owner/repo/pulls/1/mergeability",
        "gh issue create --body-file message.txt",
        "gh pr",
        "GH_TOKEN=x gh issue list",
        "env -u GH_TOKEN git status",
    )
    for command in commands:
        assert gate.decision_for(_payload(command, path)) is None, command


def test_wrapped_and_scripted_action_shapes_are_denied(tmp_path: Path) -> None:
    path = _transcript(tmp_path)
    commands = (
        'bash -c "git push"',
        "sh -lc 'gh pr create'",
        'pwsh -NoProfile -Command "git commit -F message.txt"',
        "echo `git push`",
        "python ~/.agents/skills/pull-request/scripts/pull_request.py create --title-file t.txt",
        "python3 -X utf8 'C:\\repo\\scripts\\pull_request.py' edit",
    )
    for command in commands:
        _assert_denied(_payload(command, path))


def test_wrapped_and_scripted_non_action_shapes_are_allowed(tmp_path: Path) -> None:
    path = _transcript(tmp_path)
    commands = (
        'bash -c "git status"',
        "bash script.sh",
        "cat scripts/pull_request.py",
        "python -m pytest scripts/test_pull_request.py",
        "echo `git log`",
    )
    for command in commands:
        assert gate.decision_for(_payload(command, path)) is None, command


def test_matching_github_mcp_tools_are_denied(tmp_path: Path) -> None:
    path = _transcript(tmp_path)
    for suffix in ("create_pull_request", "merge_pull_request", "enable_pr_auto_merge", "update_pull_request"):
        payload = _payload("", path, "mcp__github__" + suffix)
        _assert_denied(payload)


def test_malformed_payload_exits_zero_silently() -> None:
    assert _run_main("bad json") == (0, "")


def test_hook_has_its_own_pre_tool_use_registration() -> None:
    registration_path = HOOKS_DIRECTORY / "hooks.json"
    all_registration_fields = json.loads(registration_path.read_text(encoding="utf-8"))
    all_groups = all_registration_fields["hooks"]["PreToolUse"]
    matching_groups = [
        each_group
        for each_group in all_groups
        if each_group["matcher"]
        == "Bash|PowerShell|mcp__.*__(create_pull_request|merge_pull_request|enable_pr_auto_merge|update_pull_request)"
    ]
    assert matching_groups == [
        {
            "matcher": "Bash|PowerShell|mcp__.*__(create_pull_request|merge_pull_request|enable_pr_auto_merge|update_pull_request)",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/blocking/pr_lifecycle_skill_gate.py",
                    "timeout": 10,
                }
            ],
        }
    ]


def _checkout_without_visible_changes(tmp_path: Path) -> str:
    checkout_path = tmp_path / "checkout"
    subprocess.run(["git", "init", "-q", "-b", "main", str(checkout_path)], check=True)
    (checkout_path / "tool.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(checkout_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(checkout_path), "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "base"],
        check=True,
    )
    return str(checkout_path)


def test_loaded_skill_still_denies_a_second_followup_for_one_parent(tmp_path: Path) -> None:
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "jl-cmd", "repo": "claude-dev-env", "body": PROVEN_FOLLOWUP_BODY},
        "transcript_path": str(_transcript(tmp_path, "pr-lifecycle")),
        "cwd": _checkout_without_visible_changes(tmp_path),
    }
    open_followup = {"number": 1769, "html_url": "https://github.com/jl-cmd/claude-dev-env/pull/1769", "body": "Follow-up to #1731"}
    with patch.object(gate_dedupe, "read_open_pull_requests", return_value=[open_followup]):
        decision = gate.decision_for(payload)
    assert decision is not None
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "open follow-up pull request #1769" in decision["hookSpecificOutput"]["permissionDecisionReason"]


def test_loaded_skill_allows_a_followup_when_the_read_fails(tmp_path: Path) -> None:
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "jl-cmd", "repo": "claude-dev-env", "body": PROVEN_FOLLOWUP_BODY},
        "transcript_path": str(_transcript(tmp_path, "pr-lifecycle")),
        "cwd": _checkout_without_visible_changes(tmp_path),
    }
    with patch.object(gate_dedupe, "read_open_pull_requests", side_effect=OSError("offline")):
        assert gate.decision_for(payload) is None


def test_loaded_skill_still_denies_a_new_pull_request_without_proof(tmp_path: Path) -> None:
    exit_code, output = _run_main(_payload("gh pr create --body 'Adds a gate.'", _transcript(tmp_path, "pr-lifecycle")))
    assert exit_code == 0
    assert json.loads(output)["hookSpecificOutput"]["permissionDecisionReason"] == MISSING_PROOF_REASON


EVALUATED_BODY = (
    "## Existing work\nNothing found in open or merged pull requests.\n\n"
    "## Proof in practice\nRan `python probe.py`.\n\n"
    "## Eval\nTen labeled cases, exact-match grader. Ran `python eval.py`: 10/10.\n"
)
SKILL_LOAD_LINE = json.dumps(
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "pr-lifecycle"}}]}}
)
BUILD_EVAL_LINE = json.dumps(
    {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "claude-api", "args": "build-eval"}}]
        },
    }
)


def _transcript_with_lines(tmp_path: Path, file_name: str, all_lines: list[str]) -> Path:
    transcript_path = tmp_path / file_name
    transcript_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    return transcript_path


def _create_payload(tmp_path: Path, title: str, transcript_path: Path) -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "o", "repo": "r", "title": title, "body": EVALUATED_BODY},
        "transcript_path": str(transcript_path),
        "cwd": _checkout_without_visible_changes(tmp_path),
    }


def _assert_denied_with(payload: dict[str, object], reason: str) -> None:
    decision = gate.decision_for(payload)
    assert decision is not None
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert decision["hookSpecificOutput"]["permissionDecisionReason"] == reason


def test_feature_pull_request_without_build_eval_invocation_should_be_denied(tmp_path: Path) -> None:
    transcript_path = _transcript_with_lines(tmp_path, "session.jsonl", [SKILL_LOAD_LINE])
    _assert_denied_with(_create_payload(tmp_path, "feat: add a gate", transcript_path), MISSING_BUILD_EVAL_REASON)


def test_feature_pull_request_with_build_eval_invocation_should_pass(tmp_path: Path) -> None:
    transcript_path = _transcript_with_lines(tmp_path, "session.jsonl", [BUILD_EVAL_LINE, SKILL_LOAD_LINE])
    assert gate.decision_for(_create_payload(tmp_path, "feat: add a gate", transcript_path)) is None


def test_non_feature_pull_request_without_build_eval_invocation_should_pass(tmp_path: Path) -> None:
    transcript_path = _transcript_with_lines(tmp_path, "session.jsonl", [SKILL_LOAD_LINE])
    assert gate.decision_for(_create_payload(tmp_path, "fix: repair a gate", transcript_path)) is None


def test_feature_pull_request_with_no_readable_transcript_should_pass(tmp_path: Path) -> None:
    payload = _create_payload(tmp_path, "feat: add a gate", tmp_path / "missing.jsonl")
    assert gate.decision_for(payload) is None


def test_build_eval_check_should_ignore_an_unreadable_transcript_beside_a_readable_one(tmp_path: Path) -> None:
    transcript_path = _transcript_with_lines(tmp_path, "session.jsonl", [SKILL_LOAD_LINE])
    payload = _create_payload(tmp_path, "feat: add a gate", transcript_path)
    payload["agent_transcript_path"] = str(tmp_path / "missing-agent.jsonl")
    _assert_denied_with(payload, MISSING_BUILD_EVAL_REASON)


def test_build_eval_invocation_in_the_agent_transcript_should_pass(tmp_path: Path) -> None:
    session_path = _transcript_with_lines(tmp_path, "session.jsonl", [SKILL_LOAD_LINE])
    agent_path = _transcript_with_lines(tmp_path, "agent.jsonl", [BUILD_EVAL_LINE])
    payload = _create_payload(tmp_path, "feat: add a gate", session_path)
    payload["agent_transcript_path"] = str(agent_path)
    assert gate.decision_for(payload) is None
