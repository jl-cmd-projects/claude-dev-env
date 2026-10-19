"""Behavior tests for the owned pull request review-loop context hook.

The hook is a PostToolUse observer. It never blocks. These tests pin which
tool calls wake it, which repositories get the review-loop block, and that
every other path stays quiet. Each end-to-end test runs the script as a
subprocess with a Claude Code or Codex payload on stdin.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

try:
    advisory_directory = str(Path(__file__).resolve().parent)
    if advisory_directory not in sys.path:
        sys.path.insert(0, advisory_directory)
    import owned_pr_review_loop
except ImportError as import_error:
    raise ImportError(
        "test_owned_pr_review_loop: cannot import its sibling modules; "
        "ensure the advisory directory is importable."
    ) from import_error


HOOK_SCRIPT_PATH = Path(__file__).resolve().parent / "owned_pr_review_loop.py"
HOOKS_JSON_PATH = Path(__file__).resolve().parent.parent / "hooks.json"
OWNED_PR_URL = "https://github.com/jl-cmd-projects/claude-dev-env/pull/42"
FOREIGN_PR_URL = "https://github.com/acme/widgets/pull/3"


def _run_hook(payload: dict[str, object]) -> str:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def _shell_payload(
    command: str, stdout: str, tool_name: str = "Bash", input_key: str = "command"
) -> dict[str, object]:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": {input_key: command},
        "tool_response": {"stdout": stdout, "stderr": ""},
    }


def _mcp_payload(tool_name: str, owner: str, repository: str, url: str) -> dict[str, object]:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": {"owner": owner, "repo": repository, "title": "Add a hook"},
        "tool_response": [{"type": "text", "text": json.dumps({"id": "1", "url": url})}],
    }


def _context_of(stdout: str) -> str:
    return json.loads(stdout)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --title t --body b",
        "gh pr new --fill",
        "git push -u origin feature && gh pr create --fill",
        'pwsh -Command "gh pr create --fill"',
        "gh api repos/acme/widgets/pulls --input pr.json",
        "gh api /repos/acme/widgets/pulls -f title=t -f head=x -f base=main",
        "gh api -X POST repos/acme/widgets/pulls",
        "gh api repos/acme/widgets/pulls --input=pr.json",
        "gh api repos/acme/widgets/pulls --raw-field=title=t",
        "gh api --method=POST repos/acme/widgets/pulls",
        "gh api -XPOST repos/acme/widgets/pulls",
        "gh api repos/acme/widgets/pulls -Ftitle=t -fhead=x",
    ],
)
def test_should_detect_gh_pr_create(command: str) -> None:
    assert owned_pr_review_loop.command_creates_pull_request(command)


@pytest.mark.parametrize(
    "command",
    [
        "gh pr view 42",
        "git push -u origin feature",
        "gh pr",
        "echo gh pr create",
        "gh api repos/acme/widgets/pulls",
        "gh api repos/acme/widgets/pulls/42 -X PATCH -f state=closed",
        "gh api repos/acme/widgets/issues --input issue.json",
        "gh api --method GET repos/acme/widgets/pulls -f state=open",
        "gh api -X GET repos/acme/widgets/pulls -f state=open",
    ],
)
def test_should_not_detect_other_commands(command: str) -> None:
    assert not owned_pr_review_loop.command_creates_pull_request(command)


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__github__create_pull_request",
        "mcp__codex_apps__github_create_pull_request",
    ],
)
def test_should_treat_mcp_create_tools_as_pull_request_creation(tool_name: str) -> None:
    assert owned_pr_review_loop.tool_call_opens_pull_request(tool_name, {})


def test_should_read_the_codex_cmd_key_for_shell_tools() -> None:
    assert owned_pr_review_loop.tool_call_opens_pull_request(
        "exec_command", {"cmd": ["gh", "pr", "create", "--fill"]}
    )


def test_should_ignore_other_mcp_tools() -> None:
    assert not owned_pr_review_loop.tool_call_opens_pull_request(
        "mcp__github__merge_pull_request", {}
    )


def test_should_take_the_last_url_from_gh_output() -> None:
    pull_request = owned_pr_review_loop.opened_pull_request(
        {"command": "gh pr create"},
        {"stdout": f"Warning: see {FOREIGN_PR_URL}\n{OWNED_PR_URL}\n"},
    )
    assert pull_request == {
        "owner": "jl-cmd-projects",
        "repository": "claude-dev-env",
        "number": "42",
        "url": OWNED_PR_URL,
    }


def test_should_take_the_url_for_the_mcp_input_repository() -> None:
    pull_request = owned_pr_review_loop.opened_pull_request(
        {"owner": "JL-CMD-PROJECTS", "repo": "claude-dev-env"},
        f"Opened {OWNED_PR_URL}; see also {FOREIGN_PR_URL}",
    )
    assert pull_request is not None
    assert pull_request["number"] == "42"


def test_should_take_the_declared_url_over_urls_cited_in_the_body() -> None:
    rest_response = json.dumps(
        {
            "html_url": OWNED_PR_URL,
            "body": "Follows https://github.com/jl-cmd-projects/claude-dev-env/pull/7",
        }
    )
    pull_request = owned_pr_review_loop.opened_pull_request(
        {"command": "gh api repos/jl-cmd-projects/claude-dev-env/pulls --input pr.json"},
        {"stdout": rest_response},
    )
    assert pull_request is not None
    assert pull_request["number"] == "42"


def test_should_take_the_declared_url_from_an_mcp_text_item() -> None:
    mcp_response = [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "url": OWNED_PR_URL,
                    "body": "Replaces https://github.com/jl-cmd-projects/claude-dev-env/pull/7",
                }
            ),
        }
    ]
    pull_request = owned_pr_review_loop.opened_pull_request(
        {"owner": "jl-cmd-projects", "repo": "claude-dev-env"}, mcp_response
    )
    assert pull_request is not None
    assert pull_request["number"] == "42"


def test_should_keep_a_declared_pull_request_whose_body_says_already_exists() -> None:
    rest_response = json.dumps({"html_url": OWNED_PR_URL, "body": "The helper already exists."})
    pull_request = owned_pr_review_loop.opened_pull_request(
        {"command": "gh api repos/jl-cmd-projects/claude-dev-env/pulls --input pr.json"},
        {"stdout": rest_response},
    )
    assert pull_request is not None
    assert pull_request["url"] == OWNED_PR_URL


def test_should_find_no_pull_request_after_a_failed_command() -> None:
    assert (
        owned_pr_review_loop.opened_pull_request(
            {"command": "gh pr create"}, f"Error: Exit code 1\n{OWNED_PR_URL}"
        )
        is None
    )


def test_should_find_no_pull_request_when_one_already_exists() -> None:
    assert (
        owned_pr_review_loop.opened_pull_request(
            {"command": "gh pr create"},
            {"stdout": f'a pull request for branch "x" already exists:\n{OWNED_PR_URL}'},
        )
        is None
    )


def test_should_digest_names_in_normalized_form() -> None:
    assert owned_pr_review_loop.name_digest("Acme-Widgets/Tools") == (
        owned_pr_review_loop.name_digest("acmewidgetstools")
    )
    assert owned_pr_review_loop.name_digest("acme") != (
        owned_pr_review_loop.name_digest("acmewidgets")
    )


@pytest.mark.parametrize(
    ("owner", "repository", "expected"),
    [
        ("Acme-Widgets", "tools", True),
        ("acme-widgets", "site", True),
        ("Acme-Widgets", "reviewed", False),
        ("Other-Org", "tools", False),
    ],
)
def test_should_require_an_owned_repository_outside_the_preset_list(
    owner: str, repository: str, expected: bool
) -> None:
    all_owned_owner_digests = frozenset({owned_pr_review_loop.name_digest("acme-widgets")})
    all_preset_repository_digests = frozenset(
        {owned_pr_review_loop.name_digest("acme-widgets/reviewed")}
    )
    assert (
        owned_pr_review_loop.needs_review_loop(
            owner, repository, all_owned_owner_digests, all_preset_repository_digests
        )
        is expected
    )


@pytest.mark.parametrize(
    ("owner", "repository", "expected"),
    [
        ("jl-cmd-projects", "claude-dev-env", True),
        ("jl-cmd", "claude-dev-env", True),
        ("acme", "widgets", False),
    ],
)
def test_should_apply_the_shipped_owner_list(owner: str, repository: str, expected: bool) -> None:
    assert (
        owned_pr_review_loop.needs_review_loop(
            owner,
            repository,
            owned_pr_review_loop.ALL_OWNED_OWNER_DIGESTS,
            owned_pr_review_loop.ALL_PRESET_REPOSITORY_DIGESTS,
        )
        is expected
    )


def test_should_name_every_step_and_skill_in_the_context() -> None:
    context = owned_pr_review_loop.build_review_loop_context(
        {
            "owner": "jl-cmd-projects",
            "repository": "claude-dev-env",
            "number": "42",
            "url": OWNED_PR_URL,
        }
    )
    assert "jl-cmd-projects/claude-dev-env#42" in context
    assert "efficient-review" in context
    assert "gh pr ready 42 --repo jl-cmd-projects/claude-dev-env" in context
    assert "poteto-mode/playbooks/babysit.md" in context
    assert "poteto-mode/playbooks/shipping.md" in context
    assert "merged" in context


def test_should_carry_the_owner_approval_to_merge() -> None:
    context = owned_pr_review_loop.build_review_loop_context(
        {
            "owner": "jl-cmd-projects",
            "repository": "claude-dev-env",
            "number": "42",
            "url": OWNED_PR_URL,
        }
    )
    assert "The repository owner installed this hook" in context
    assert "approves every step above, the merge included" in context
    assert "without asking first" in context
    assert "Your task now runs past opening this PR to its merge" in context


def test_main_should_emit_the_loop_after_gh_pr_create_on_an_owned_repository() -> None:
    stdout = _run_hook(_shell_payload("gh pr create --fill", f"{OWNED_PR_URL}\n"))
    payload = json.loads(stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "efficient-review" in _context_of(stdout)


def test_main_should_emit_the_loop_after_a_gh_api_pulls_post() -> None:
    rest_response = json.dumps(
        {
            "url": "https://api.github.com/repos/jl-cmd-projects/claude-dev-env/pulls/42",
            "html_url": OWNED_PR_URL,
            "_links": {"html": {"href": OWNED_PR_URL}},
        }
    )
    stdout = _run_hook(
        _shell_payload("gh api repos/jl-cmd-projects/claude-dev-env/pulls --input pr.json", rest_response)
    )
    assert "jl-cmd-projects/claude-dev-env#42" in _context_of(stdout)


def test_main_should_emit_the_loop_for_a_codex_shell_call() -> None:
    stdout = _run_hook(
        _shell_payload(
            "gh pr create --fill", f"{OWNED_PR_URL}\n", tool_name="exec_command", input_key="cmd"
        )
    )
    assert OWNED_PR_URL in _context_of(stdout)


@pytest.mark.parametrize(
    "tool_name",
    ["mcp__github__create_pull_request", "mcp__codex_apps__github_create_pull_request"],
)
def test_main_should_emit_the_loop_after_an_mcp_create(tool_name: str) -> None:
    stdout = _run_hook(
        _mcp_payload(
            tool_name,
            "jl-cmd-projects",
            "DeepStack",
            "https://github.com/jl-cmd-projects/DeepStack/pull/9",
        )
    )
    assert "jl-cmd-projects/DeepStack#9" in _context_of(stdout)


def test_main_should_stay_quiet_for_a_repository_we_do_not_own() -> None:
    assert _run_hook(_shell_payload("gh pr create --fill", f"{FOREIGN_PR_URL}\n")) == ""


def test_main_should_stay_quiet_for_a_command_that_opens_no_pull_request() -> None:
    assert _run_hook(_shell_payload("gh pr view 42", f"{OWNED_PR_URL}\n")) == ""


def test_main_should_stay_quiet_for_a_failed_create() -> None:
    payload = _shell_payload("gh pr create --fill", "")
    payload["tool_response"] = "Error: Exit code 1\npull request create failed"
    assert _run_hook(payload) == ""


def test_hooks_json_should_route_shell_and_mcp_create_calls_to_the_hook() -> None:
    hooks_config = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    all_matchers = [
        each_group["matcher"]
        for each_group in hooks_config["hooks"]["PostToolUse"]
        if any(
            "advisory/owned_pr_review_loop.py" in each_hook.get("command", "")
            for each_hook in each_group["hooks"]
        )
    ]
    assert len(all_matchers) == 1
    for each_tool_name in (
        "Bash",
        "PowerShell",
        "exec_command",
        "shell_command",
        "mcp__github__create_pull_request",
        "mcp__codex_apps__github_create_pull_request",
    ):
        assert re.fullmatch(all_matchers[0], each_tool_name), each_tool_name
