"""Behavior tests for the one-follow-up-pull-request-per-parent check."""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
from collections.abc import Mapping
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import followup_pr_dedupe as dedupe
from blocking.gate_run_reads import gate_run
from hooks_constants.followup_pr_dedupe_constants import (
    DUPLICATE_FOLLOWUP_REASON_TEMPLATE,
    UNANSWERED_FOLLOWUP_REASON_TEMPLATE,
    GH_REPO_SET_FOLLOWUP_REASON_TEMPLATE,
    UNREAD_ORIGIN_FOLLOWUP_REASON_TEMPLATE,
)
from hooks_constants.pytest_invocation import unquoted_token

OPEN_FOLLOWUP = {
    "number": 1769,
    "html_url": "https://github.com/jl-cmd/claude-dev-env/pull/1769",
    "body": "Follow-up to #1731. Fixes one smell.",
}
OTHER_FOLLOWUP = {
    "number": 1777,
    "html_url": "https://github.com/jl-cmd/claude-dev-env/pull/1777",
    "body": "follow-up to #17",
}


def _reader(all_open: list[Mapping[str, object]]) -> dedupe.OpenPullRequestReader:
    def read(owner: str, repo: str) -> list[Mapping[str, object]]:
        assert (owner, repo) == ("jl-cmd", "claude-dev-env")
        return all_open

    return read


def _failing_reader(*_all_reader_arguments: str) -> list[Mapping[str, object]]:
    raise OSError("network down")


def _mcp_payload(body: str) -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "jl-cmd", "repo": "claude-dev-env", "body": body},
    }


def test_second_followup_for_one_parent_is_denied() -> None:
    reason = dedupe.duplicate_followup_reason(
        _mcp_payload("FOLLOW-UP TO #1731: another smell"), _reader([OTHER_FOLLOWUP, OPEN_FOLLOWUP])
    )
    assert reason is not None
    assert "#1769" in reason
    assert "Add this finding to the open follow-up pull request #1769" in reason


def test_first_followup_passes() -> None:
    assert dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #1731"), _reader([OTHER_FOLLOWUP])) is None


def test_parent_prefix_number_does_not_match_longer_parent() -> None:
    assert dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #173"), _reader([OPEN_FOLLOWUP])) is None


def test_non_followup_pull_request_skips_the_read() -> None:
    assert dedupe.duplicate_followup_reason(_mcp_payload("Adds a hook."), _failing_reader) is None


def test_read_failure_fails_open() -> None:
    assert dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #1731"), _failing_reader) is None


def test_gh_pr_create_inline_body_is_denied() -> None:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "gh pr create -R jl-cmd/claude-dev-env --title t --body 'Follow-up to #1731'"},
    }
    reason = dedupe.duplicate_followup_reason(payload, _reader([OPEN_FOLLOWUP]))
    assert reason is not None and "pull request #1769" in reason


def test_powershell_body_file_is_denied(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text("Follow-up to #1731\n", encoding="utf-8")
    payload = {
        "tool_name": "PowerShell",
        "cwd": str(tmp_path),
        "tool_input": {"command": "gh pr create --repo jl-cmd/claude-dev-env --body-file body.md"},
    }
    reason = dedupe.duplicate_followup_reason(payload, _reader([OPEN_FOLLOWUP]))
    assert reason is not None and "pull request #1769" in reason


def test_body_from_arguments_reads_inline_text_and_body_files(tmp_path: Path) -> None:
    (tmp_path / "body.md").write_text("From the file.", encoding="utf-8")
    assert dedupe.body_from_arguments(["--body", "Inline."], "") == "Inline."
    assert dedupe.body_from_arguments(["--body-file", "body.md"], str(tmp_path)) == "From the file."
    assert dedupe.body_from_arguments(["--body-file", "-"], str(tmp_path)) is None
    assert dedupe.body_from_arguments(["--fill"], str(tmp_path)) is None


def test_body_from_arguments_should_read_only_a_regular_body_file(tmp_path: Path) -> None:
    assert dedupe.body_from_arguments(["--body-file", os.devnull], str(tmp_path)) is None
    assert dedupe.body_from_arguments(["--body-file", "."], str(tmp_path)) is None


def _trickling_server() -> ThreadingHTTPServer:
    class TrickleHandler(BaseHTTPRequestHandler):
        def log_message(self, *all_arguments: object) -> None:
            return

        def do_GET(self) -> None:
            payload = json.dumps([OPEN_FOLLOWUP]).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            for each_byte in payload:
                self.wfile.write(bytes([each_byte]))
                self.wfile.flush()
                time.sleep(0.3)

    server = ThreadingHTTPServer(("127.0.0.1", 0), TrickleHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_read_open_pull_requests_should_bound_the_whole_read(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _trickling_server()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setattr(dedupe, "GITHUB_API_ROOT", f"http://127.0.0.1:{server.server_address[1]}")
    monkeypatch.setattr(dedupe, "READ_TIMEOUT_SECONDS", 1)
    with pytest.raises(TimeoutError):
        dedupe.read_open_pull_requests("jl-cmd", "claude-dev-env")
    server.shutdown()


def test_shell_command_should_return_only_a_shell_tool_command() -> None:
    assert dedupe.shell_command({"tool_name": "PowerShell", "tool_input": {"command": "git push"}}) == "git push"
    assert dedupe.shell_command({"tool_name": "Read", "tool_input": {"command": "git push"}}) is None
    assert dedupe.shell_command({"tool_name": "Bash", "tool_input": {"command": 7}}) is None


def test_all_command_segments_should_list_each_segment_and_wrapped_command() -> None:
    all_segments = list(dedupe.all_command_segments("git add x && bash -c 'git push'"))
    assert ["git", "add", "x"] in all_segments
    assert ["git", "push"] in all_segments


def test_title_from_arguments_should_read_each_title_flag_shape() -> None:
    assert dedupe.title_from_arguments(["--title", "feat: x", "--fill"]) == "feat: x"
    assert dedupe.title_from_arguments(["-t", "fix: y"]) == "fix: y"
    assert dedupe.title_from_arguments(["--title=feat(x): z"]) == "feat(x): z"
    assert dedupe.title_from_arguments(["--title-file", "t.txt"]) is None
    assert dedupe.title_from_arguments(["--fill"]) is None


def _dispatch_payload(all_inputs: dict[str, object]) -> dict[str, object]:
    return {
        "tool_name": "mcp__github__actions_run_trigger",
        "tool_input": {"method": "run_workflow", "owner": "jl-cmd", "repo": "claude-dev-env", "inputs": all_inputs},
    }


def test_create_tool_fields_should_read_a_pull_request_dispatch_as_a_create() -> None:
    payload = _dispatch_payload({"head": "b", "title": "fix: y", "body": "Follow-up to #1731"})
    assert dedupe.create_tool_fields(payload) == {
        "head": "b",
        "title": "fix: y",
        "body": "Follow-up to #1731",
        "owner": "jl-cmd",
        "repo": "claude-dev-env",
    }
    reason = dedupe.duplicate_followup_reason(payload, _reader([OPEN_FOLLOWUP]))
    assert reason is not None and "#1769" in reason


def test_create_tool_fields_should_skip_a_call_that_opens_no_pull_request() -> None:
    assert dedupe.create_tool_fields(_dispatch_payload({"work_order": "wo-1"})) is None
    assert dedupe.create_tool_fields({"tool_name": "Bash", "tool_input": {"command": "gh pr list"}}) is None


def _open_followup(number: int, parent_number: int) -> dict[str, object]:
    return {
        "number": number,
        "html_url": f"https://github.com/o/r/pull/{number}",
        "body": f"Follow-up to #{parent_number}",
    }


def _duplicate_reason(open_followup: Mapping[str, object], parent_number: int) -> str:
    return DUPLICATE_FOLLOWUP_REASON_TEMPLATE.format(
        open_number=open_followup["number"], parent_number=parent_number, open_url=open_followup["html_url"]
    )


def _keyed_reader(
    all_open_by_repository: Mapping[tuple[str, str], list[Mapping[str, object]] | Exception],
    all_asked_repositories: list[tuple[str, str]],
) -> dedupe.OpenPullRequestReader:
    def read(owner: str, repo: str) -> list[Mapping[str, object]]:
        all_asked_repositories.append((owner, repo))
        answer = all_open_by_repository[(owner, repo)]
        if isinstance(answer, Exception):
            raise answer
        return answer

    return read


def _chained_inline_creates(all_repositories_and_bodies: list[tuple[str, str]]) -> dict[str, object]:
    all_creates = [
        f'gh pr create --repo {each_repository} --title "fix: {each_index}" --body "{each_body}"'
        for each_index, (each_repository, each_body) in enumerate(all_repositories_and_bodies)
    ]
    return {"tool_name": "Bash", "tool_input": {"command": " && ".join(all_creates)}}


def test_chained_creates_should_deny_when_only_the_second_body_repeats_an_open_followup() -> None:
    open_followup = _open_followup(9, 7)
    all_asked_repositories: list[tuple[str, str]] = []
    payload = _chained_inline_creates([("o/r", "Adds a hook."), ("o/r", "Follow-up to #7")])
    reason = dedupe.duplicate_followup_reason(
        payload, _keyed_reader({("o", "r"): [open_followup]}, all_asked_repositories)
    )
    assert reason == _duplicate_reason(open_followup, 7)


def test_followup_drafts_should_count_a_quoted_create_once() -> None:
    payload = _chained_inline_creates([("o/r", "Follow-up to #7"), ("o/r", "Follow-up to #8")])
    assert dedupe.followup_drafts(payload) == [
        dedupe.PullRequestDraft("o", "r", "Follow-up to #7"),
        dedupe.PullRequestDraft("o", "r", "Follow-up to #8"),
    ]


def test_chained_followups_should_read_one_open_list_per_repository() -> None:
    open_followup = _open_followup(11, 8)
    all_asked_repositories: list[tuple[str, str]] = []
    payload = _chained_inline_creates([("o/r", "Follow-up to #7"), ("o/r", "Follow-up to #8")])
    with gate_run():
        reason = dedupe.duplicate_followup_reason(
            payload, _keyed_reader({("o", "r"): [open_followup]}, all_asked_repositories)
        )
    assert reason == _duplicate_reason(open_followup, 8)
    assert all_asked_repositories == [("o", "r")]


def test_followup_read_failure_should_skip_only_that_create() -> None:
    open_followup = _open_followup(9, 7)
    all_asked_repositories: list[tuple[str, str]] = []
    all_open_by_repository: dict[tuple[str, str], list[Mapping[str, object]] | Exception] = {
        ("a", "r"): OSError("network down"),
        ("b", "r"): [open_followup],
    }
    payload = _chained_inline_creates([("a/r", "Follow-up to #5"), ("b/r", "Follow-up to #7")])
    reason = dedupe.duplicate_followup_reason(payload, _keyed_reader(all_open_by_repository, all_asked_repositories))
    assert reason == _duplicate_reason(open_followup, 7)
    assert all_asked_repositories == [("a", "r"), ("b", "r")]


def _unanswered_reason(owner: str, repo: str, parent_number: int) -> str:
    return UNANSWERED_FOLLOWUP_REASON_TEMPLATE.format(owner=owner, repo=repo, parent_number=parent_number)


def _raising_reader(error: Exception) -> dedupe.OpenPullRequestReader:
    def read(owner: str, repo: str) -> list[Mapping[str, object]]:
        raise error

    return read


@pytest.mark.parametrize(
    "unanswered_error",
    [
        TimeoutError("read timed out"),
        urllib.error.URLError(TimeoutError("connect timed out")),
        urllib.error.HTTPError("https://api.github.com/x", 500, "Internal Server Error", Message(), None),
        urllib.error.HTTPError("https://api.github.com/x", 503, "Service Unavailable", Message(), None),
    ],
)
def test_unanswered_read_should_refuse_the_create(unanswered_error: Exception) -> None:
    reason = dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #1731"), _raising_reader(unanswered_error))
    assert reason == _unanswered_reason("jl-cmd", "claude-dev-env", 1731)


@pytest.mark.parametrize(
    "answered_error",
    [
        urllib.error.HTTPError("https://api.github.com/x", 404, "Not Found", Message(), None),
        urllib.error.HTTPError("https://api.github.com/x", 403, "rate limit exceeded", Message(), None),
        urllib.error.HTTPError("https://api.github.com/x", 429, "Too Many Requests", Message(), None),
        urllib.error.URLError(ConnectionRefusedError("refused")),
        urllib.error.URLError(OSError("Name or service not known")),
        json.JSONDecodeError("Expecting value", "<html>", 0),
    ],
)
def test_answered_read_failure_should_skip_the_create(answered_error: Exception) -> None:
    assert dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #1731"), _raising_reader(answered_error)) is None


def test_read_with_no_time_left_should_refuse_the_create(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dedupe, "answer_within_allowance", lambda *all_arguments: None)
    reason = dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #1731"))
    assert reason == _unanswered_reason("jl-cmd", "claude-dev-env", 1731)


def _silent_server() -> ThreadingHTTPServer:
    class SilentHandler(BaseHTTPRequestHandler):
        def log_message(self, *all_arguments: object) -> None:
            return

        def do_GET(self) -> None:
            time.sleep(5)

    server = ThreadingHTTPServer(("127.0.0.1", 0), SilentHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_hung_web_read_should_refuse_the_create(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _silent_server()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setattr(dedupe, "GITHUB_API_ROOT", f"http://127.0.0.1:{server.server_address[1]}")
    monkeypatch.setattr(dedupe, "READ_TIMEOUT_SECONDS", 1)
    reason = dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #1731"))
    server.shutdown()
    assert reason == _unanswered_reason("jl-cmd", "claude-dev-env", 1731)


def test_web_read_answering_404_should_skip_the_create(monkeypatch: pytest.MonkeyPatch) -> None:
    class NotFoundHandler(BaseHTTPRequestHandler):
        def log_message(self, *all_arguments: object) -> None:
            return

        def do_GET(self) -> None:
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), NotFoundHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setattr(dedupe, "GITHUB_API_ROOT", f"http://127.0.0.1:{server.server_address[1]}")
    reason = dedupe.duplicate_followup_reason(_mcp_payload("Follow-up to #1731"))
    server.shutdown()
    assert reason is None


def test_unanswered_read_should_refuse_every_draft_on_that_repository_after_one_read() -> None:
    all_asked_repositories: list[tuple[str, str]] = []
    reader = _keyed_reader({("o", "r"): TimeoutError("read timed out")}, all_asked_repositories)
    with gate_run():
        first_reason = dedupe.duplicate_followup_reason(_chained_inline_creates([("o/r", "Follow-up to #7")]), reader)
        second_reason = dedupe.duplicate_followup_reason(_chained_inline_creates([("o/r", "Follow-up to #8")]), reader)
    assert first_reason == _unanswered_reason("o", "r", 7)
    assert second_reason == _unanswered_reason("o", "r", 8)
    assert all_asked_repositories == [("o", "r")]


def test_answered_failure_should_stay_remembered_as_a_skip() -> None:
    all_asked_repositories: list[tuple[str, str]] = []
    reader = _keyed_reader({("o", "r"): OSError("network down")}, all_asked_repositories)
    with gate_run():
        first_reason = dedupe.duplicate_followup_reason(_chained_inline_creates([("o/r", "Follow-up to #7")]), reader)
        second_reason = dedupe.duplicate_followup_reason(_chained_inline_creates([("o/r", "Follow-up to #8")]), reader)
    assert (first_reason, second_reason) == (None, None)
    assert all_asked_repositories == [("o", "r")]


def test_first_unanswered_or_duplicate_draft_in_command_order_should_refuse() -> None:
    open_followup = _open_followup(9, 7)
    all_open_by_repository: dict[tuple[str, str], list[Mapping[str, object]] | Exception] = {
        ("a", "r"): TimeoutError("read timed out"),
        ("b", "r"): [open_followup],
    }
    all_asked_repositories: list[tuple[str, str]] = []
    unanswered_first = _chained_inline_creates([("a/r", "Follow-up to #5"), ("b/r", "Follow-up to #7")])
    reader = _keyed_reader(all_open_by_repository, all_asked_repositories)
    assert dedupe.duplicate_followup_reason(unanswered_first, reader) == _unanswered_reason("a", "r", 5)
    assert all_asked_repositories == [("a", "r")]
    duplicate_first = _chained_inline_creates([("b/r", "Follow-up to #7"), ("a/r", "Follow-up to #5")])
    assert dedupe.duplicate_followup_reason(duplicate_first, reader) == _duplicate_reason(open_followup, 7)


def _script_create(command: str, tmp_path: Path, body: str) -> dict[str, object]:
    (tmp_path / "body.md").write_text(body, encoding="utf-8")
    return {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {"command": command}}


def test_script_create_whose_body_file_names_an_open_parent_should_be_denied(tmp_path: Path) -> None:
    payload = _script_create(
        "python3 .agents/skills/pull-request/scripts/pull_request.py create --repo jl-cmd/claude-dev-env"
        ' --base main --head fix-b --title "fix: b" --body-file body.md',
        tmp_path,
        "Follow-up to #1731\n",
    )
    reason = dedupe.duplicate_followup_reason(payload, _reader([OPEN_FOLLOWUP]))
    assert reason == _duplicate_reason(OPEN_FOLLOWUP, 1731)


def test_followup_drafts_should_read_a_script_create_once_with_its_assigned_options(tmp_path: Path) -> None:
    payload = _script_create(
        'python pull_request.py create --repo=o/r --base=main --head=b --title="fix: b" --body-file=body.md',
        tmp_path,
        "Follow-up to #7\n",
    )
    assert dedupe.followup_drafts(payload) == [dedupe.PullRequestDraft("o", "r", "Follow-up to #7\n")]


def test_all_create_argument_lists_should_list_gh_and_script_creates_once_each() -> None:
    command = (
        'gh pr create --title "fix: a" --body x'
        ' && python3 pull_request.py create --repo o/r --title "fix: b" --body-file b.md'
        " && python3 pull_request.py edit --repo o/r --number 7 && gh pr view 7"
    )
    all_argument_lists = [
        [unquoted_token(each_argument) for each_argument in each_list]
        for each_list in dedupe.all_create_argument_lists(command)
    ]
    assert all_argument_lists == [
        ["--title", "fix: a", "--body", "x"],
        ["--repo", "o/r", "--title", "fix: b", "--body-file", "b.md"],
    ]


@pytest.mark.parametrize(
    ("command", "expected_arguments"),
    [
        ("gh pr new --title t", ["--title", "t"]),
        ("gh -R o/r pr create --title t", ["--title", "t", "-R", "o/r"]),
        ("gh --repo o/r pr create", ["--repo", "o/r"]),
        ("gh --repo=o/r pr new", ["--repo=o/r"]),
        ("GH_REPO=o/r gh pr create --title t", ["--title", "t", "--repo", "o/r"]),
        ("env GH_REPO=o/r gh pr create", ["--repo", "o/r"]),
        ("GH_REPO=x/y gh pr create --repo o/r", ["--repo", "o/r"]),
        ("python3.11 pull_request.py create --title t", ["--title", "t"]),
        ("python3.13 pull_request.py create", []),
        ("python3 -u pull_request.py create", []),
        ("python -X dev pull_request.py create --head h", ["--head", "h"]),
        ("py -3 pull_request.py create", []),
        ("uv run python pull_request.py create", []),
        ("uv run pull_request.py create", []),
        ("python3 ~/.agents/skills/pull-request/scripts/pull_request.py create", []),
    ],
)
def test_all_create_argument_lists_should_read_every_create_spelling(
    command: str, expected_arguments: list[str]
) -> None:
    all_argument_lists = [
        [unquoted_token(each_argument) for each_argument in each_list]
        for each_list in dedupe.all_create_argument_lists(command)
    ]
    assert all_argument_lists == [expected_arguments]


@pytest.mark.parametrize(
    "command",
    [
        "python -m pull_request.py create",
        'python -c "print(1)" pull_request.py create',
        'git commit -m "see gh pr create --head two"',
        "cat <<'EOF'\ngh pr create --head two\nEOF",
        "gh pr view --repo o/r",
    ],
)
def test_all_create_argument_lists_should_skip_text_that_runs_no_create(command: str) -> None:
    assert list(dedupe.all_create_argument_lists(command)) == []


def test_create_arguments_should_read_one_segment() -> None:
    assert dedupe.create_arguments(["GH_REPO=o/r", "gh", "pr", "new", "--head", "h"]) == [
        "--head",
        "h",
        "--repo",
        "o/r",
    ]
    assert dedupe.create_arguments(["gh", "pr", "view"]) is None


def test_option_value_should_read_spaced_and_assigned_values() -> None:
    assert dedupe.option_value(["--head", "a", "--head", "b"], frozenset({"--head"})) == "a"
    assert dedupe.option_value(["-H='c'"], frozenset({"-H", "--head"})) == "c"
    assert dedupe.option_value(["--fill"], frozenset({"--head"})) is None


@pytest.mark.parametrize(
    ("all_tokens", "expected"),
    [
        (["GH_REPO=o/r", "gh", "pr", "view"], "o/r"),
        (["X=1", "GH_REPO=o/r", "gh.exe", "pr", "view"], "o/r"),
        (["gh", "pr", "view", "GH_REPO=o/r"], None),
        (["gh", "pr", "view"], None),
        (["GH_REPO=a/b", "GH_REPO=o/r", "gh", "pr", "view"], "o/r"),
        (["GH_REPO+=o/r", "gh", "pr", "view"], None),
        (["GH_REPO=o/r", "GH_REPO+=x", "gh", "pr", "view"], None),
        (["GH_REPO+=x", "GH_REPO=o/r", "gh", "pr", "view"], "o/r"),
    ],
)
def test_prefix_repository_should_read_only_a_prefix_before_gh(all_tokens: list[str], expected: str | None) -> None:
    assert dedupe.prefix_repository(all_tokens) == expected


def test_named_repository_should_read_owner_and_name_past_a_host() -> None:
    assert dedupe.named_repository("github.com/o/r") == ("o", "r")
    assert dedupe.named_repository("o/r") == ("o", "r")
    assert dedupe.named_repository("notaslug") is None


def test_gh_repo_environment_should_name_the_repository_when_the_origin_is_unread(tmp_path: Path) -> None:
    all_asked_repositories: list[tuple[str, str]] = []
    open_followup = _open_followup(9, 7)
    payload = {
        "tool_name": "Bash",
        "cwd": str(tmp_path),
        "tool_input": {"command": 'GH_REPO=o/r gh pr create --title "fix: a" --body "Follow-up to #7"'},
    }
    reader = _keyed_reader({("o", "r"): [open_followup]}, all_asked_repositories)
    assert dedupe.duplicate_followup_reason(payload, reader) == _duplicate_reason(open_followup, 7)
    assert all_asked_repositories == [("o", "r")]


@pytest.mark.parametrize(
    "command",
    [
        'GH_REPO=o/r env -u GH_REPO gh pr create --title "fix: a" --body "Follow-up to #7"',
        'GH_REPO=o/r env -i gh pr create --title "fix: a" --body "Follow-up to #7"',
        'gh pr create --repo o/r --title "fix: a" --body "Follow-up to #7" ; '
        'GH_REPO=o/r gh pr create --title "fix: a" --body "Follow-up to #7"',
    ],
)
def test_should_find_an_origin_duplicate_for_a_create_behind_a_gh_repo_prefix(
    tmp_path: Path, command: str
) -> None:
    checkout_path = _checkout_with_origin(tmp_path, "https://github.com/acme/tools.git")
    open_followup = _open_followup(9, 7)
    all_asked_repositories: list[tuple[str, str]] = []
    payload = {"tool_name": "Bash", "cwd": str(checkout_path), "tool_input": {"command": command}}
    reader = _keyed_reader({("o", "r"): [], ("acme", "tools"): [open_followup]}, all_asked_repositories)
    assert dedupe.duplicate_followup_reason(payload, reader) == _duplicate_reason(open_followup, 7)
    assert ("acme", "tools") in all_asked_repositories


def test_should_allow_a_create_that_names_its_repository_with_its_own_repo_flag_when_origin_holds_a_duplicate(
    tmp_path: Path,
) -> None:
    checkout_path = _checkout_with_origin(tmp_path, "https://github.com/acme/tools.git")
    all_asked_repositories: list[tuple[str, str]] = []
    command = 'gh pr create --repo o/r --title "fix: a" --body "Follow-up to #7"'
    payload = {"tool_name": "Bash", "cwd": str(checkout_path), "tool_input": {"command": command}}
    reader = _keyed_reader({("o", "r"): [], ("acme", "tools"): [_open_followup(9, 7)]}, all_asked_repositories)
    assert dedupe.duplicate_followup_reason(payload, reader) is None
    assert all_asked_repositories == [("o", "r")]


def test_all_pull_request_argument_lists_should_list_the_named_action_only() -> None:
    command = "gh pr edit 7 --body x && python pull_request.py edit --number 8 && gh pr create --body y"
    all_argument_lists = list(dedupe.all_pull_request_argument_lists(command, ["pr", "edit"], "edit"))
    assert all_argument_lists == [["7", "--body", "x"], ["--number", "8"]]


def _unread_origin_reason(parent_number: int) -> str:
    return UNREAD_ORIGIN_FOLLOWUP_REASON_TEMPLATE.format(parent_number=parent_number)


def _create_without_repository(working_directory: Path, body: str) -> dict[str, object]:
    return {
        "tool_name": "Bash",
        "cwd": str(working_directory),
        "tool_input": {"command": f'gh pr create --title "fix: a" --body "{body}"'},
    }


def _checkout_with_origin(tmp_path: Path, origin_url: str) -> Path:
    checkout_path = tmp_path / "checkout"
    subprocess.run(["git", "init", "-q", str(checkout_path)], check=True)
    subprocess.run(["git", "-C", str(checkout_path), "remote", "add", "origin", origin_url], check=True)
    return checkout_path


def _unasked_reader(all_asked_repositories: list[tuple[str, str]]) -> dedupe.OpenPullRequestReader:
    return _keyed_reader({}, all_asked_repositories)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("export GH_REPO=o/r ; gh pr create", True),
        ("GH_REPO=o/r && gh pr create", True),
        ("declare -x GH_REPO", True),
        ("typeset -x GH_REPO=o/r", True),
        ("bash -c 'export GH_REPO=o/r'", True),
        ("env GH_REPO=o/r bash -c 'gh pr create'", True),
        ("export GH_REPO+=o/r ; gh pr create", True),
        ("GH_REPO+=o/r ; gh pr create", True),
        ("declare -x GH_REPO+=o/r", True),
        ("GH_REPO+=o/r gh pr create", True),
        ("GH_REPO+=o/r bash -c 'gh pr create'", True),
        ("GH_REPO=o/r gh pr create", False),
        ("echo GH_REPO=o/r ; gh pr create", False),
        ("echo GH_REPO+=o/r ; gh pr create", False),
        ("gh pr create --body 'export GH_REPO=o/r'", False),
        ("export PATH=/bin ; gh pr create", False),
    ],
)
def test_sets_gh_repository_should_find_a_gh_repo_set_outside_a_create_prefix(command: str, expected: bool) -> None:
    assert dedupe.sets_gh_repository(command) is expected


@pytest.mark.parametrize("operator", [";", "&&", "\n"])
def test_create_with_no_repository_should_be_refused_when_the_command_sets_gh_repo(
    tmp_path: Path, operator: str
) -> None:
    all_asked_repositories: list[tuple[str, str]] = []
    checkout = _checkout_with_origin(tmp_path, "https://github.com/acme/tools.git")
    create = 'gh pr create --title "fix: a" --body "Follow-up to #7"'
    payload = {
        "tool_name": "Bash",
        "cwd": str(checkout),
        "tool_input": {"command": f"export GH_REPO=o/r {operator} {create}"},
    }
    reason = dedupe.duplicate_followup_reason(payload, _unasked_reader(all_asked_repositories))
    assert reason == GH_REPO_SET_FOLLOWUP_REASON_TEMPLATE.format(parent_number=7)
    assert all_asked_repositories == []


@pytest.mark.parametrize(
    "prefix",
    ["GH_REPO+=o/r ", "export GH_REPO+=o/r ; ", "GH_REPO+=o/r ; ", "GH_REPO=acme/tools GH_REPO+=x "],
)
def test_create_with_no_repository_should_be_refused_when_the_command_appends_to_gh_repo(
    tmp_path: Path, prefix: str
) -> None:
    all_asked_repositories: list[tuple[str, str]] = []
    checkout = _checkout_with_origin(tmp_path, "https://github.com/acme/tools.git")
    create = 'gh pr create --title "fix: a" --body "Follow-up to #7"'
    payload = {"tool_name": "Bash", "cwd": str(checkout), "tool_input": {"command": prefix + create}}
    reason = dedupe.duplicate_followup_reason(payload, _unasked_reader(all_asked_repositories))
    assert reason == GH_REPO_SET_FOLLOWUP_REASON_TEMPLATE.format(parent_number=7)
    assert all_asked_repositories == []


def test_create_with_its_own_repository_should_be_read_when_the_command_appends_to_gh_repo(tmp_path: Path) -> None:
    all_asked_repositories: list[tuple[str, str]] = []
    open_followup = _open_followup(9, 7)
    command = 'GH_REPO+=x/y gh pr create --repo o/r --title "fix: a" --body "Follow-up to #7"'
    payload = {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {"command": command}}
    reader = _keyed_reader({("o", "r"): [open_followup]}, all_asked_repositories)
    assert dedupe.duplicate_followup_reason(payload, reader) == _duplicate_reason(open_followup, 7)
    assert all_asked_repositories == [("o", "r")]


def test_create_with_its_own_repository_should_be_read_when_the_command_sets_gh_repo(tmp_path: Path) -> None:
    all_asked_repositories: list[tuple[str, str]] = []
    open_followup = _open_followup(9, 7)
    command = 'export GH_REPO=x/y ; gh pr create --repo o/r --title "fix: a" --body "Follow-up to #7"'
    payload = {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {"command": command}}
    reader = _keyed_reader({("o", "r"): [open_followup]}, all_asked_repositories)
    assert dedupe.duplicate_followup_reason(payload, reader) == _duplicate_reason(open_followup, 7)
    assert all_asked_repositories == [("o", "r")]


def test_origin_read_that_outlives_its_allowance_should_refuse_the_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dedupe, "ALL_GIT_REMOTE_COMMAND_WORDS", (sys.executable, "-c", "import time; time.sleep(5)"))
    monkeypatch.setattr(dedupe, "READ_TIMEOUT_SECONDS", 1)
    all_asked_repositories: list[tuple[str, str]] = []
    payload = _create_without_repository(tmp_path, "Follow-up to #1731")
    reason = dedupe.duplicate_followup_reason(payload, _unasked_reader(all_asked_repositories))
    assert reason == _unread_origin_reason(1731)
    assert all_asked_repositories == []


def test_origin_read_that_exits_non_zero_should_refuse_the_create(tmp_path: Path) -> None:
    all_asked_repositories: list[tuple[str, str]] = []
    payload = _create_without_repository(tmp_path, "Follow-up to #1731")
    reason = dedupe.duplicate_followup_reason(payload, _unasked_reader(all_asked_repositories))
    assert reason == _unread_origin_reason(1731)
    assert all_asked_repositories == []


def test_origin_that_prints_a_url_off_github_should_skip_the_create(tmp_path: Path) -> None:
    checkout_path = _checkout_with_origin(tmp_path, "https://gitlab.com/o/r.git")
    all_asked_repositories: list[tuple[str, str]] = []
    payload = _create_without_repository(checkout_path, "Follow-up to #1731")
    assert dedupe.duplicate_followup_reason(payload, _unasked_reader(all_asked_repositories)) is None
    assert all_asked_repositories == []


def test_origin_on_github_should_name_the_repository_to_read(tmp_path: Path) -> None:
    checkout_path = _checkout_with_origin(tmp_path, "git@github.com:o/r.git")
    all_asked_repositories: list[tuple[str, str]] = []
    payload = _create_without_repository(checkout_path, "Follow-up to #7")
    reader = _keyed_reader({("o", "r"): [_open_followup(9, 7)]}, all_asked_repositories)
    assert dedupe.duplicate_followup_reason(payload, reader) == _duplicate_reason(_open_followup(9, 7), 7)
    assert all_asked_repositories == [("o", "r")]


def test_unread_origin_should_be_read_once_per_run_and_refuse_every_draft_without_a_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_origin_reads: list[tuple[object, ...]] = []

    def unanswered_child(*all_arguments: object) -> None:
        all_origin_reads.append(all_arguments)

    monkeypatch.setattr(dedupe, "child_stdout", unanswered_child)
    all_asked_repositories: list[tuple[str, str]] = []
    with gate_run():
        first_reason = dedupe.duplicate_followup_reason(
            _create_without_repository(tmp_path, "Follow-up to #7"), _unasked_reader(all_asked_repositories)
        )
        second_reason = dedupe.duplicate_followup_reason(
            _create_without_repository(tmp_path, "Follow-up to #8"), _unasked_reader(all_asked_repositories)
        )
    assert (first_reason, second_reason) == (_unread_origin_reason(7), _unread_origin_reason(8))
    assert len(all_origin_reads) == 1


def test_command_order_should_decide_between_an_unread_origin_and_a_duplicate(tmp_path: Path) -> None:
    open_followup = _open_followup(9, 7)
    with_repository = 'gh pr create --repo b/r --title "fix: b" --body "Follow-up to #7"'
    without_repository = 'gh pr create --title "fix: a" --body "Follow-up to #5"'
    reader = _keyed_reader({("b", "r"): [open_followup]}, [])

    def payload(command: str) -> dict[str, object]:
        return {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {"command": command}}

    unread_first = payload(without_repository + " && " + with_repository)
    duplicate_first = payload(with_repository + " && " + without_repository)
    assert dedupe.duplicate_followup_reason(unread_first, reader) == _unread_origin_reason(5)
    assert dedupe.duplicate_followup_reason(duplicate_first, reader) == _duplicate_reason(open_followup, 7)


def test_repository_value_gh_rejects_should_skip_the_create(tmp_path: Path) -> None:
    all_asked_repositories: list[tuple[str, str]] = []
    payload = {
        "tool_name": "Bash",
        "cwd": str(tmp_path),
        "tool_input": {"command": 'gh pr create --repo notaslug --title "fix: a" --body "Follow-up to #7"'},
    }
    assert dedupe.duplicate_followup_reason(payload, _unasked_reader(all_asked_repositories)) is None
    assert all_asked_repositories == []
