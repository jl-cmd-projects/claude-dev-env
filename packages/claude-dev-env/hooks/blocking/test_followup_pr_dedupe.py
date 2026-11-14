"""Behavior tests for the one-follow-up-pull-request-per-parent check."""

import json
import os
import sys
import threading
import time
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking import followup_pr_dedupe as dedupe
from blocking.gate_run_reads import gate_run
from hooks_constants.followup_pr_dedupe_constants import DUPLICATE_FOLLOWUP_REASON_TEMPLATE

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
