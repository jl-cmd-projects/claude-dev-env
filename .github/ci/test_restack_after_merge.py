"""Specifications for restacking open stack levels after a lower level squash-merges.

Each scenario builds a bare origin and two clones in a temporary directory, merges
level 1 into main by squash the way the merge queue does, deletes its branch, and
runs the script from a fresh clone with a stub `gh` on PATH that records each call.
"""

import json
import os
import re
import shlex
import stat
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

_CI_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_CI_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_SCRIPTS_DIR))

import restack_after_merge

from config.restack_after_merge_constants import (
    NEEDS_REBASE_LABEL,
    REASON_PUSH_REJECTED,
    RESTACK_COMMENT_MARKER_TEMPLATE,
)

REPOSITORY = "example-owner/example-repo"
WORKFLOW_PATH = _CI_SCRIPTS_DIR.parent / "workflows" / "restack-after-merge.yml"
MERGED_PULL_REQUEST_NUMBER = 1

STUB_GH_SOURCE = textwrap.dedent(
    """
    import json, os, subprocess, sys, urllib.parse
    state_path = os.environ["STUB_GH_STATE"]
    state = json.load(open(state_path))
    all_arguments = sys.argv[1:]
    with open(os.environ["STUB_GH_LOG"], "a") as log_file:
        log_file.write(json.dumps(all_arguments) + "\\n")
    def save():
        json.dump(state, open(state_path, "w"), indent=1)
    def option(name):
        return all_arguments[all_arguments.index(name) + 1]
    if all_arguments[:2] == ["api", "graphql"]:
        nodes = []
        for each in state["pulls"]:
            events = [{"__typename": "AutomaticBaseChangeSucceededEvent", "oldBase": each["previousBase"]}] if each.get("previousBase") else []
            nodes.append({"number": each["number"], "headRefName": each["head"], "baseRefName": each["base"],
                          "isCrossRepository": each.get("cross", False), "timelineItems": {"nodes": events},
                          "labels": {"nodes": [{"name": label} for label in each.get("labels", [])]}})
        print(json.dumps({"data": {"repository": {"pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}))
    elif all_arguments[0] == "api" and "/rules/branches/" in all_arguments[2]:
        branch = urllib.parse.unquote(all_arguments[2].split("/rules/branches/", 1)[1])
        if branch in state.get("unreadableRules", []):
            sys.exit("stub gh: rules read failed")
        print("\\n".join(state.get("branchRules", {}).get(branch, [])))
    elif all_arguments[0] == "api" and "/branches/" in all_arguments[1]:
        branch = urllib.parse.unquote(all_arguments[1].split("/branches/", 1)[1])
        if branch in state.get("unreadableBranches", []):
            sys.exit("stub gh: branch read failed")
        print("true" if branch in state.get("protectedBranches", []) else "false")
    elif all_arguments[0] == "api" and all_arguments[-2] == "--jq":
        number = all_arguments[2].split("/")[-2]
        print("\\n".join(state["comments"].get(number, [])))
    elif all_arguments[:2] == ["pr", "edit"]:
        if all_arguments[2] in state.get("failingEdits", []):
            sys.exit("stub gh: edit failed")
        pull = next(each for each in state["pulls"] if str(each["number"]) == all_arguments[2])
        if "--base" in all_arguments:
            pull["previousBase"], pull["base"] = pull["base"], option("--base")
            if pull.get("pushDuringBaseEdit"):
                subprocess.run(pull.pop("pushDuringBaseEdit"), check=True)
        if "--add-label" in all_arguments:
            pull["labels"] = sorted(set(pull.get("labels", [])) | {option("--add-label")})
        if "--remove-label" in all_arguments:
            pull["labels"] = sorted(set(pull.get("labels", [])) - {option("--remove-label")})
        save()
    elif all_arguments[:2] == ["pr", "view"]:
        print(next(each["base"] for each in state["pulls"] if str(each["number"]) == all_arguments[2]))
    elif all_arguments[:2] == ["pr", "comment"]:
        state["comments"].setdefault(all_arguments[2], []).append(option("--body"))
        save()
    else:
        sys.exit("stub gh: unhandled " + " ".join(all_arguments))
    """
)


def run_git(working_directory: Path, *all_arguments: str) -> str:
    completed_process = subprocess.run(
        ["git", *all_arguments],
        cwd=working_directory,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed_process.stdout.strip()


def commit_file(clone_path: Path, file_name: str, file_text: str, message: str) -> str:
    (clone_path / file_name).write_text(file_text, encoding="utf-8")
    run_git(clone_path, "add", file_name)
    run_git(clone_path, "commit", "-q", "-m", message)
    return run_git(clone_path, "rev-parse", "HEAD")


@dataclass
class StackSandbox:
    """A bare origin, a developer clone that builds the stack, and a runner clone for the script."""

    root_path: Path
    all_pulls: list[dict] = field(default_factory=list)

    @property
    def origin_path(self) -> Path:
        return self.root_path / "origin.git"

    @property
    def developer_path(self) -> Path:
        return self.root_path / "developer"

    @property
    def runner_path(self) -> Path:
        return self.root_path / "runner"

    @property
    def state_path(self) -> Path:
        return self.root_path / "gh_state.json"

    @property
    def log_path(self) -> Path:
        return self.root_path / "gh_calls.jsonl"

    def create(self) -> None:
        run_git(
            self.root_path, "init", "-q", "--bare", "-b", "main", str(self.origin_path)
        )
        run_git(
            self.root_path,
            "clone",
            "-q",
            str(self.origin_path),
            str(self.developer_path),
        )
        commit_file(self.developer_path, "shared.txt", "line one\nline two\n", "base")
        run_git(self.developer_path, "push", "-q", "origin", "main")

    def branch(self, branch_name: str, start_point: str) -> None:
        run_git(self.developer_path, "checkout", "-q", "-B", branch_name, start_point)

    def push_branch(self, branch_name: str) -> str:
        run_git(
            self.developer_path,
            "push",
            "-q",
            "--force",
            "origin",
            f"{branch_name}:refs/heads/{branch_name}",
        )
        return run_git(self.developer_path, "rev-parse", branch_name)

    def open_pull(
        self, number: int, head: str, base: str, **extra_fields: object
    ) -> None:
        self.all_pulls.append(
            {"number": number, "head": head, "base": base, **extra_fields}
        )

    def squash_merge(
        self, number: int, branch_name: str, squash: bool = True
    ) -> tuple[str, str]:
        head_sha = self.push_branch(branch_name)
        run_git(
            self.developer_path,
            "push",
            "-q",
            "origin",
            f"{head_sha}:refs/pull/{number}/head",
        )
        run_git(self.developer_path, "checkout", "-q", "main")
        if squash:
            run_git(self.developer_path, "merge", "-q", "--squash", branch_name)
            run_git(
                self.developer_path,
                "commit",
                "-q",
                "-m",
                f"level {number} squashed (#{number})",
            )
        else:
            run_git(
                self.developer_path,
                "merge",
                "-q",
                "--no-ff",
                "-m",
                f"level {number} merged (#{number})",
                branch_name,
            )
        run_git(
            self.developer_path,
            "push",
            "-q",
            "origin",
            "main",
            f":refs/heads/{branch_name}",
        )
        for each_pull in self.all_pulls:
            if each_pull["base"] == branch_name:
                each_pull["previousBase"], each_pull["base"] = branch_name, "main"
        self.all_pulls = [each for each in self.all_pulls if each["number"] != number]
        return head_sha, run_git(self.developer_path, "rev-parse", "main")

    def write_stub_state(self) -> None:
        self.state_path.write_text(
            json.dumps({"pulls": self.all_pulls, "comments": {}}), encoding="utf-8"
        )

    def read_stub_state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def read_stub_calls(self) -> list[list[str]]:
        if not self.log_path.exists():
            return []
        return [
            json.loads(each_line)
            for each_line in self.log_path.read_text(encoding="utf-8").splitlines()
        ]

    def origin_head(self, branch_name: str) -> str:
        return run_git(self.origin_path, "rev-parse", f"refs/heads/{branch_name}")

    def subjects_above(self, base_sha: str, branch_name: str) -> list[str]:
        return run_git(
            self.origin_path,
            "log",
            "--format=%s",
            "--reverse",
            f"{base_sha}..refs/heads/{branch_name}",
        ).splitlines()

    def run_restack(self, merged_head_sha: str, merge_commit_sha: str) -> int:
        if not self.runner_path.exists():
            run_git(
                self.root_path,
                "clone",
                "-q",
                str(self.origin_path),
                str(self.runner_path),
            )
        previous_directory = Path.cwd()
        os.chdir(self.runner_path)
        try:
            return restack_after_merge.main(
                [
                    "--repo",
                    REPOSITORY,
                    "--merged-pr",
                    str(MERGED_PULL_REQUEST_NUMBER),
                    "--merged-head-ref",
                    "level-1",
                    "--merged-head-sha",
                    merged_head_sha,
                    "--merge-commit-sha",
                    merge_commit_sha,
                    "--base-ref",
                    "main",
                    "--default-branch",
                    "main",
                ],
                error_stream=sys.stderr,
            )
        finally:
            os.chdir(previous_directory)


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StackSandbox:
    stub_directory = tmp_path / "bin"
    stub_directory.mkdir()
    stub_gh_path = stub_directory / "gh"
    stub_gh_path.write_text(f"#!{sys.executable}\n{STUB_GH_SOURCE}", encoding="utf-8")
    stub_gh_path.chmod(stub_gh_path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{stub_directory}{os.pathsep}{os.environ['PATH']}")
    for each_name in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(each_name, "Stack Tester")
    for each_name in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(each_name, "stack-tester@example.com")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("STUB_GH_STATE", str(tmp_path / "gh_state.json"))
    monkeypatch.setenv("STUB_GH_LOG", str(tmp_path / "gh_calls.jsonl"))
    stack_sandbox = StackSandbox(root_path=tmp_path)
    stack_sandbox.create()
    return stack_sandbox


def build_three_level_stack(sandbox: StackSandbox) -> dict[str, str]:
    """Level 1 gets an extra commit after level 2 branches, and level 3 sits on level 2."""
    sandbox.branch("level-1", "main")
    commit_file(sandbox.developer_path, "one.txt", "level one\n", "level 1 first")
    sandbox.branch("level-2", "level-1")
    commit_file(sandbox.developer_path, "two.txt", "level two\n", "level 2 work")
    level_2_tree = run_git(sandbox.developer_path, "rev-parse", "level-2^{tree}")
    sandbox.branch("level-3", "level-2")
    commit_file(sandbox.developer_path, "three.txt", "level three\n", "level 3 work")
    sandbox.branch("level-1", "level-1")
    commit_file(
        sandbox.developer_path,
        "one.txt",
        "level one\nextra after level 2 branched\n",
        "level 1 extra",
    )
    for each_branch in ("level-2", "level-3"):
        sandbox.push_branch(each_branch)
    sandbox.open_pull(2, "level-2", "level-1")
    sandbox.open_pull(3, "level-3", "level-2")
    return {"level_2_tree": level_2_tree}


def test_should_leave_each_level_with_only_its_own_commits_on_main(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    assert sandbox.run_restack(merged_head_sha, merge_commit_sha) == 0

    assert sandbox.subjects_above(merge_commit_sha, "level-2") == ["level 2 work"]
    assert sandbox.subjects_above(sandbox.origin_head("level-2"), "level-3") == [
        "level 3 work"
    ]
    assert run_git(sandbox.origin_path, "rev-parse", "level-2~1") == merge_commit_sha
    assert (
        run_git(sandbox.origin_path, "show", "level-3:one.txt")
        == "level one\nextra after level 2 branched"
    )
    assert {
        each["number"]: each["base"] for each in sandbox.read_stub_state()["pulls"]
    } == {2: "main", 3: "level-2"}


def test_should_push_nothing_when_run_again(sandbox: StackSandbox) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    sandbox.run_restack(merged_head_sha, merge_commit_sha)
    all_heads_after_first_run = {
        each: sandbox.origin_head(each) for each in ("level-2", "level-3")
    }
    sandbox.branch("main", "origin/main")
    commit_file(sandbox.developer_path, "later.txt", "later\n", "later work on main")
    run_git(sandbox.developer_path, "push", "-q", "origin", "main")

    assert sandbox.run_restack(merged_head_sha, merge_commit_sha) == 0

    assert {
        each: sandbox.origin_head(each) for each in ("level-2", "level-3")
    } == all_heads_after_first_run
    assert sandbox.read_stub_state()["comments"] == {}


def test_should_restack_a_child_whose_parent_was_amended_after_it_branched(
    sandbox: StackSandbox,
) -> None:
    sandbox.branch("level-1", "main")
    commit_file(sandbox.developer_path, "one.txt", "level one\n", "level 1 first")
    sandbox.branch("level-2", "level-1")
    commit_file(sandbox.developer_path, "two.txt", "level two\n", "level 2 work")
    sandbox.push_branch("level-2")
    sandbox.branch("level-1", "level-1")
    run_git(
        sandbox.developer_path,
        "commit",
        "-q",
        "--amend",
        "-m",
        "level 1 first, reworded",
    )
    commit_file(
        sandbox.developer_path, "one.txt", "level one\nlevel one follow-up\n", "level 1 follow-up"
    )
    sandbox.open_pull(2, "level-2", "level-1")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert sandbox.subjects_above(merge_commit_sha, "level-2") == ["level 2 work"]


def test_should_label_and_comment_once_on_a_conflict_and_leave_the_level_above(
    sandbox: StackSandbox,
) -> None:
    sandbox.branch("level-1", "main")
    commit_file(
        sandbox.developer_path,
        "shared.txt",
        "line one\nlevel one version\n",
        "level 1 first",
    )
    sandbox.branch("level-2", "level-1")
    commit_file(
        sandbox.developer_path,
        "shared.txt",
        "line one\nlevel two version\n",
        "level 2 work",
    )
    sandbox.branch("level-3", "level-2")
    commit_file(sandbox.developer_path, "three.txt", "level three\n", "level 3 work")
    all_heads_before = {
        each: sandbox.push_branch(each) for each in ("level-2", "level-3")
    }
    sandbox.branch("level-1", "level-1")
    commit_file(
        sandbox.developer_path,
        "shared.txt",
        "line one\nlevel one rewritten\n",
        "level 1 rewritten",
    )
    sandbox.branch("level-2-sibling", "level-1")
    commit_file(sandbox.developer_path, "sibling.txt", "sibling\n", "sibling work")
    sandbox.push_branch("level-2-sibling")
    sandbox.open_pull(2, "level-2", "level-1")
    sandbox.open_pull(3, "level-3", "level-2")
    sandbox.open_pull(4, "level-2-sibling", "level-1")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    sandbox.run_restack(merged_head_sha, merge_commit_sha)
    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert run_git(sandbox.origin_path, "rev-parse", "level-2-sibling~1") == merge_commit_sha

    stub_state = sandbox.read_stub_state()
    level_2_comments = stub_state["comments"]["2"]
    assert {
        each: sandbox.origin_head(each) for each in ("level-2", "level-3")
    } == all_heads_before
    assert (
        NEEDS_REBASE_LABEL
        in next(each for each in stub_state["pulls"] if each["number"] == 2)["labels"]
    )
    assert len(level_2_comments) == 1
    assert level_2_comments[0].startswith(
        RESTACK_COMMENT_MARKER_TEMPLATE % MERGED_PULL_REQUEST_NUMBER
    )
    assert "git push --force-with-lease=level-2 origin level-2" in level_2_comments[0]
    assert "3" not in stub_state["comments"]


def test_should_label_and_comment_when_the_push_is_refused(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    level_2_head_before = sandbox.origin_head("level-2")
    refusing_hook_path = sandbox.origin_path / "hooks" / "pre-receive"
    refusing_hook_path.write_text(
        "#!/bin/sh\necho 'refusing workflow edits' >&2\nexit 1\n", encoding="utf-8"
    )
    refusing_hook_path.chmod(0o755)

    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert sandbox.origin_head("level-2") == level_2_head_before
    assert REASON_PUSH_REJECTED in sandbox.read_stub_state()["comments"]["2"][0]


def test_should_keep_a_commit_pushed_after_the_fetch(sandbox: StackSandbox) -> None:
    build_three_level_stack(sandbox)
    sandbox.branch("level-2", "level-2")
    late_commit_sha = commit_file(
        sandbox.developer_path, "late.txt", "late\n", "pushed while the restack ran"
    )
    sandbox.all_pulls[0]["pushDuringBaseEdit"] = [
        "git", "-C", str(sandbox.developer_path), "push", "-q", "--force", "origin",
        f"{late_commit_sha}:refs/heads/level-2",
    ]
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.all_pulls[0]["base"] = "level-1"
    sandbox.write_stub_state()

    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert sandbox.origin_head("level-2") == late_commit_sha


def test_should_leave_an_unrelated_pull_request_on_main_alone(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    sandbox.branch("unrelated", "main")
    commit_file(sandbox.developer_path, "other.txt", "other\n", "unrelated work")
    unrelated_head = sandbox.push_branch("unrelated")
    sandbox.open_pull(9, "unrelated", "main")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert sandbox.origin_head("unrelated") == unrelated_head
    assert not any(
        each_call[:3] == ["pr", "edit", "9"] for each_call in sandbox.read_stub_calls()
    )


def test_should_find_a_child_on_main_that_shares_an_unmerged_commit(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    sandbox.all_pulls[0]["base"] = "main"
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert sandbox.subjects_above(merge_commit_sha, "level-2") == ["level 2 work"]


def test_should_read_the_previous_base_from_either_base_change_event() -> None:
    def node_with(event: dict) -> dict:
        return {
            "number": 4,
            "headRefName": "h",
            "baseRefName": "main",
            "isCrossRepository": False,
            "timelineItems": {"nodes": [event]},
            "labels": {"nodes": []},
        }

    assert (
        restack_after_merge.parse_open_pull_request(
            node_with({"previousRefName": "level-1"})
        ).previous_base_ref
        == "level-1"
    )
    assert (
        restack_after_merge.parse_open_pull_request(
            node_with({"oldBase": "level-1"})
        ).previous_base_ref
        == "level-1"
    )


def test_should_not_treat_a_fork_pull_request_as_a_child() -> None:
    fork_pull_request = restack_after_merge.OpenPullRequest(
        number=5,
        head_ref="level-2",
        base_ref="level-1",
        previous_base_ref=None,
        is_cross_repository=True,
    )
    merged_pull_request = restack_after_merge.MergedPullRequest(
        number=1,
        head_ref="level-1",
        head_sha="0" * 40,
        merge_commit_sha="1" * 40,
        base_ref="main",
    )

    assert not restack_after_merge.is_direct_child(
        fork_pull_request, merged_pull_request, "origin", "main", "2" * 40
    )


def test_should_name_the_lease_and_fork_point_in_the_manual_comment(
    sandbox: StackSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_three_level_stack(sandbox)
    fork_sha = run_git(sandbox.developer_path, "rev-parse", "level-2~1")
    target = restack_after_merge.RestackTarget(
        pull_request=restack_after_merge.OpenPullRequest(
            2, "level-2", "level-1", None, False
        ),
        onto_branch="main",
        onto_sha="unused",
        upstream_sha=fork_sha,
        settled_sha="unused",
    )
    merged_pull_request = restack_after_merge.MergedPullRequest(
        1, "level-1", fork_sha, "unused", "main"
    )
    monkeypatch.chdir(sandbox.developer_path)

    comment_body = restack_after_merge.build_manual_restack_comment(
        target, merged_pull_request, "abc123", "the rebase hit a conflict", "origin", REPOSITORY
    )

    assert f"git rebase --onto origin/main {fork_sha}" in comment_body
    assert "git push --force-with-lease=level-2 origin level-2" in comment_body


def test_should_parse_the_merged_pull_request_flags() -> None:
    parsed_arguments = restack_after_merge.parse_command_line_arguments(
        [
            "--repo",
            REPOSITORY,
            "--merged-pr",
            "7",
            "--merged-head-ref",
            "h",
            "--merged-head-sha",
            "s",
            "--merge-commit-sha",
            "m",
            "--base-ref",
            "main",
            "--default-branch",
            "trunk",
        ]
    )

    assert (
        parsed_arguments.merged_pr,
        parsed_arguments.remote,
        parsed_arguments.default_branch,
    ) == (7, "origin", "trunk")


def test_should_return_one_when_the_merged_head_cannot_be_fetched(
    sandbox: StackSandbox,
) -> None:
    sandbox.write_stub_state()

    assert sandbox.run_restack("f" * 40, "e" * 40) == 1


def test_should_report_every_visited_level(sandbox: StackSandbox, monkeypatch: pytest.MonkeyPatch) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    run_git(
        sandbox.root_path,
        "clone",
        "-q",
        str(sandbox.origin_path),
        str(sandbox.runner_path),
    )
    monkeypatch.chdir(sandbox.runner_path)
    merged_pull_request = restack_after_merge.MergedPullRequest(
        1, "level-1", merged_head_sha, merge_commit_sha, "main"
    )

    all_outcomes = restack_after_merge.restack_after_merge(
        REPOSITORY, merged_pull_request, "origin", "main"
    )

    assert all_outcomes == [
        (2, restack_after_merge.RestackOutcome.RESTACKED),
        (3, restack_after_merge.RestackOutcome.RESTACKED),
    ]


def run_restack_for_outcomes(
    sandbox: StackSandbox,
    merged_head_sha: str,
    merge_commit_sha: str,
    default_branch: str = "main",
) -> dict[int, restack_after_merge.RestackOutcome]:
    run_git(
        sandbox.root_path,
        "clone",
        "-q",
        str(sandbox.origin_path),
        str(sandbox.runner_path),
    )
    previous_directory = Path.cwd()
    os.chdir(sandbox.runner_path)
    try:
        return dict(
            restack_after_merge.restack_after_merge(
                REPOSITORY,
                restack_after_merge.MergedPullRequest(
                    1, "level-1", merged_head_sha, merge_commit_sha, "main"
                ),
                "origin",
                default_branch,
            )
        )
    finally:
        os.chdir(previous_directory)


def test_should_never_rewrite_the_default_branch_stacked_on_a_level(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    sandbox.open_pull(7, "main", "level-2")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    all_outcomes = run_restack_for_outcomes(sandbox, merged_head_sha, merge_commit_sha)

    assert sandbox.origin_head("main") == merge_commit_sha
    assert all_outcomes[7] is restack_after_merge.RestackOutcome.DEFAULT_BRANCH_REFUSED


def test_should_skip_a_child_that_carries_none_of_the_stack_commits(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    sandbox.branch("unrelated", "main")
    commit_file(sandbox.developer_path, "other.txt", "other\n", "unrelated work")
    unrelated_head = sandbox.push_branch("unrelated")
    sandbox.open_pull(8, "unrelated", "level-1")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    all_outcomes = run_restack_for_outcomes(sandbox, merged_head_sha, merge_commit_sha)

    assert sandbox.origin_head("unrelated") == unrelated_head
    assert all_outcomes[8] is restack_after_merge.RestackOutcome.NOT_STACKED
    assert "carries none of the merged" in sandbox.read_stub_state()["comments"]["8"][0]
    assert all_outcomes[2] is restack_after_merge.RestackOutcome.RESTACKED


def test_should_quote_every_branch_name_in_the_manual_commands(
    sandbox: StackSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_three_level_stack(sandbox)
    fork_sha = run_git(sandbox.developer_path, "rev-parse", "level-2~1")
    hostile_head = "level-2$(touch pwned)"
    hostile_base = "main;id"
    target = restack_after_merge.RestackTarget(
        pull_request=restack_after_merge.OpenPullRequest(
            2, hostile_head, "level-1", None, False
        ),
        onto_branch=hostile_base,
        onto_sha="unused",
        upstream_sha=fork_sha,
        settled_sha="unused",
    )
    merged_pull_request = restack_after_merge.MergedPullRequest(
        1, "level-1", fork_sha, "unused", hostile_base
    )
    monkeypatch.chdir(sandbox.developer_path)

    comment_body = restack_after_merge.build_manual_restack_comment(
        target, merged_pull_request, "abc123", "the rebase hit a conflict", "origin", REPOSITORY
    )
    all_command_lines = (
        comment_body.split("```bash\n", 1)[1].split("```", 1)[0].splitlines()
    )

    assert [shlex.split(each_line) for each_line in all_command_lines] == [
        ["git", "fetch", "origin", hostile_base, hostile_head],
        ["git", "switch", "-C", hostile_head, f"origin/{hostile_head}"],
        ["git", "rebase", "--onto", f"origin/{hostile_base}", fork_sha],
        ["git", "push", f"--force-with-lease={hostile_head}", "origin", hostile_head],
        ["gh", "pr", "edit", "2", "--repo", REPOSITORY, "--base", hostile_base],
        ["gh", "pr", "edit", "2", "--remove-label", NEEDS_REBASE_LABEL],
    ]


def build_branch_stacked_on_level_2(sandbox: StackSandbox, branch_name: str) -> str:
    sandbox.branch(branch_name, "level-2")
    commit_file(
        sandbox.developer_path, f"{branch_name.replace('/', '-')}.txt", f"{branch_name}\n", f"{branch_name} work"
    )
    return sandbox.push_branch(branch_name)


def test_should_never_rewrite_a_default_branch_that_is_not_the_merged_base(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    develop_head = build_branch_stacked_on_level_2(sandbox, "develop")
    sandbox.open_pull(7, "develop", "level-2")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    all_outcomes = run_restack_for_outcomes(
        sandbox, merged_head_sha, merge_commit_sha, default_branch="develop"
    )

    assert sandbox.origin_head("develop") == develop_head
    assert all_outcomes[7] is restack_after_merge.RestackOutcome.DEFAULT_BRANCH_REFUSED
    assert all_outcomes[3] is restack_after_merge.RestackOutcome.RESTACKED


def test_should_never_rewrite_a_protected_branch_or_one_whose_protection_cannot_be_read(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    guarded_head = build_branch_stacked_on_level_2(sandbox, "guarded/release")
    unreadable_head = build_branch_stacked_on_level_2(sandbox, "unreadable")
    sandbox.open_pull(9, "guarded/release", "level-2")
    sandbox.open_pull(10, "unreadable", "level-2")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    stub_state = sandbox.read_stub_state()
    stub_state["protectedBranches"] = ["guarded/release"]
    stub_state["unreadableBranches"] = ["unreadable"]
    sandbox.state_path.write_text(json.dumps(stub_state), encoding="utf-8")

    all_outcomes = run_restack_for_outcomes(sandbox, merged_head_sha, merge_commit_sha)

    assert sandbox.origin_head("guarded/release") == guarded_head
    assert sandbox.origin_head("unreadable") == unreadable_head
    assert all_outcomes[9] is restack_after_merge.RestackOutcome.PROTECTED_BRANCH_REFUSED
    assert all_outcomes[10] is restack_after_merge.RestackOutcome.PROTECTED_BRANCH_REFUSED
    assert all_outcomes[3] is restack_after_merge.RestackOutcome.RESTACKED


def test_should_skip_an_unrelated_child_when_the_merged_level_holds_a_merge_commit(
    sandbox: StackSandbox,
) -> None:
    sandbox.branch("side", "main")
    commit_file(sandbox.developer_path, "side.txt", "side\n", "side work")
    sandbox.branch("level-1", "main")
    commit_file(sandbox.developer_path, "one.txt", "level one\n", "level 1 first")
    run_git(sandbox.developer_path, "merge", "-q", "--no-ff", "-m", "merge side into level 1", "side")
    sandbox.branch("unrelated", "main")
    commit_file(sandbox.developer_path, "other.txt", "other\n", "unrelated work")
    unrelated_head = sandbox.push_branch("unrelated")
    sandbox.open_pull(8, "unrelated", "level-1")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    all_outcomes = run_restack_for_outcomes(sandbox, merged_head_sha, merge_commit_sha)

    assert sandbox.origin_head("unrelated") == unrelated_head
    assert all_outcomes[8] is restack_after_merge.RestackOutcome.NOT_STACKED


def test_should_refuse_a_branch_whose_rules_guard_its_history_and_allow_other_rules(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    all_heads_before = {
        each_branch: build_branch_stacked_on_level_2(sandbox, each_branch)
        for each_branch in ("no-force-push", "rules-unreadable", "checks-only")
    }
    sandbox.open_pull(11, "no-force-push", "level-2")
    sandbox.open_pull(12, "rules-unreadable", "level-2")
    sandbox.open_pull(13, "checks-only", "level-2")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    stub_state = sandbox.read_stub_state()
    stub_state["branchRules"] = {
        "no-force-push": ["required_status_checks", "non_fast_forward"],
        "checks-only": ["required_status_checks", "pull_request"],
    }
    stub_state["unreadableRules"] = ["rules-unreadable"]
    sandbox.state_path.write_text(json.dumps(stub_state), encoding="utf-8")

    all_outcomes = run_restack_for_outcomes(sandbox, merged_head_sha, merge_commit_sha)

    assert sandbox.origin_head("no-force-push") == all_heads_before["no-force-push"]
    assert sandbox.origin_head("rules-unreadable") == all_heads_before["rules-unreadable"]
    assert all_outcomes[11] is restack_after_merge.RestackOutcome.PROTECTED_BRANCH_REFUSED
    assert all_outcomes[12] is restack_after_merge.RestackOutcome.PROTECTED_BRANCH_REFUSED
    assert all_outcomes[13] is restack_after_merge.RestackOutcome.RESTACKED
    assert sandbox.subjects_above(sandbox.origin_head("level-2"), "checks-only") == [
        "checks-only work"
    ]


def render_workflow_expressions(template: str, all_values_by_expression: dict[str, str]) -> str:
    return re.sub(
        r"\$\{\{\s*(.+?)\s*\}\}",
        lambda each_match: all_values_by_expression[each_match.group(1)],
        template,
    )


def test_should_give_each_merged_pull_request_its_own_concurrency_group() -> None:
    concurrency = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["concurrency"]

    def group_for(merged_number: int) -> str:
        return render_workflow_expressions(
            concurrency["group"],
            {
                "github.repository": REPOSITORY,
                "github.event.pull_request.number": str(merged_number),
            },
        )

    assert len({group_for(2), group_for(3), group_for(4)}) == 3
    assert concurrency["cancel-in-progress"] is False


def run_manual_git_commands(comment_body: str, clone_path: Path) -> list[int]:
    all_command_lines = (
        comment_body.split("```bash\n", 1)[1].split("```", 1)[0].splitlines()
    )
    return [
        subprocess.run(
            shlex.split(each_line), cwd=clone_path, capture_output=True, text=True, check=False
        ).returncode
        for each_line in all_command_lines
        if each_line.startswith("git ")
    ]


def test_should_let_the_pasted_commands_push_after_the_branch_moved_past_the_refused_push(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    refusing_hook_path = sandbox.origin_path / "hooks" / "pre-receive"
    refusing_hook_path.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    refusing_hook_path.chmod(0o755)
    sandbox.run_restack(merged_head_sha, merge_commit_sha)
    refusing_hook_path.unlink()
    sandbox.branch("level-2", "level-2")
    commit_file(sandbox.developer_path, "late.txt", "late\n", "pushed after the refusal")
    sandbox.push_branch("level-2")
    hand_clone_path = sandbox.root_path / "hand"
    run_git(sandbox.root_path, "clone", "-q", str(sandbox.origin_path), str(hand_clone_path))

    all_exit_codes = run_manual_git_commands(
        sandbox.read_stub_state()["comments"]["2"][0], hand_clone_path
    )

    assert all_exit_codes == [0, 0, 0, 0]
    assert sandbox.subjects_above(merge_commit_sha, "level-2") == [
        "level 2 work",
        "pushed after the refusal",
    ]


def test_should_restack_the_levels_above_one_that_landed_with_a_merge_commit(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1", squash=False
    )
    sandbox.write_stub_state()

    all_outcomes = run_restack_for_outcomes(sandbox, merged_head_sha, merge_commit_sha)

    assert all_outcomes == {
        2: restack_after_merge.RestackOutcome.RESTACKED,
        3: restack_after_merge.RestackOutcome.RESTACKED,
    }
    assert sandbox.subjects_above(merge_commit_sha, "level-2") == ["level 2 work"]
    assert sandbox.read_stub_state()["comments"] == {}


def test_should_leave_a_pull_request_its_author_moved_off_the_merged_level(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    sandbox.branch("integration", "main")
    commit_file(sandbox.developer_path, "integration.txt", "integration\n", "integration work")
    sandbox.push_branch("integration")
    sandbox.branch("moved", "level-2~1")
    commit_file(sandbox.developer_path, "moved.txt", "moved\n", "moved work")
    moved_head = sandbox.push_branch("moved")
    sandbox.open_pull(6, "moved", "integration", previousBase="level-1")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    all_outcomes = run_restack_for_outcomes(sandbox, merged_head_sha, merge_commit_sha)

    assert sandbox.origin_head("moved") == moved_head
    assert 6 not in all_outcomes
    assert not any(each_call[:3] == ["pr", "edit", "6"] for each_call in sandbox.read_stub_calls())
    assert all_outcomes[2] is restack_after_merge.RestackOutcome.RESTACKED


def test_should_restack_the_other_levels_when_one_base_edit_fails_and_exit_nonzero(
    sandbox: StackSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    build_three_level_stack(sandbox)
    level_2_head_before = sandbox.origin_head("level-2")
    sandbox.branch("level-2-sibling", "level-2~1")
    commit_file(sandbox.developer_path, "sibling.txt", "sibling\n", "sibling work")
    sandbox.push_branch("level-2-sibling")
    sandbox.open_pull(4, "level-2-sibling", "level-1")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.all_pulls[0]["base"] = "level-1"
    sandbox.write_stub_state()
    stub_state = sandbox.read_stub_state()
    stub_state["failingEdits"] = ["2"]
    sandbox.state_path.write_text(json.dumps(stub_state), encoding="utf-8")

    exit_code = sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert exit_code == 1
    assert sandbox.origin_head("level-2") == level_2_head_before
    assert sandbox.subjects_above(merge_commit_sha, "level-2-sibling") == ["sibling work"]
    assert "#2" in capsys.readouterr().err


def test_should_restack_the_other_levels_when_flagging_one_fails_and_exit_nonzero(
    sandbox: StackSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    build_three_level_stack(sandbox)
    sandbox.branch("unrelated", "main")
    commit_file(sandbox.developer_path, "other.txt", "other\n", "unrelated work")
    sandbox.push_branch("unrelated")
    sandbox.all_pulls.insert(0, {"number": 8, "head": "unrelated", "base": "level-1"})
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    stub_state = sandbox.read_stub_state()
    stub_state["failingEdits"] = ["8"]
    sandbox.state_path.write_text(json.dumps(stub_state), encoding="utf-8")

    exit_code = sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert exit_code == 1
    assert sandbox.subjects_above(merge_commit_sha, "level-2") == ["level 2 work"]
    assert sandbox.subjects_above(sandbox.origin_head("level-2"), "level-3") == ["level 3 work"]
    assert "#8" in capsys.readouterr().err


def test_should_drop_the_needs_rebase_label_from_a_level_it_restacks(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    sandbox.all_pulls[0]["labels"] = [NEEDS_REBASE_LABEL, "type: feature"]
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()

    assert sandbox.run_restack(merged_head_sha, merge_commit_sha) == 0

    all_labels_by_number = {
        each["number"]: each.get("labels", []) for each in sandbox.read_stub_state()["pulls"]
    }
    assert all_labels_by_number == {2: ["type: feature"], 3: []}
    assert not any(each_call[:3] == ["pr", "edit", "3"] for each_call in sandbox.read_stub_calls())


def test_should_judge_a_child_on_main_against_the_base_head_the_run_fetched(
    sandbox: StackSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_three_level_stack(sandbox)
    level_1_head = sandbox.push_branch("level-1")
    run_git(sandbox.developer_path, "fetch", "-q", "origin")
    monkeypatch.chdir(sandbox.developer_path)
    child_on_main = restack_after_merge.OpenPullRequest(2, "level-2", "main", None, False)
    merged_pull_request = restack_after_merge.MergedPullRequest(
        1, "level-1", level_1_head, "unused", "main"
    )
    fetched_main_head = run_git(sandbox.developer_path, "rev-parse", "origin/main")

    assert restack_after_merge.is_direct_child(
        child_on_main, merged_pull_request, "origin", "main", fetched_main_head
    )
    assert not restack_after_merge.is_direct_child(
        child_on_main, merged_pull_request, "origin", "main", level_1_head
    )


def install_refusing_hook(sandbox: StackSandbox, hook_body: str) -> Path:
    refusing_hook_path = sandbox.origin_path / "hooks" / "pre-receive"
    refusing_hook_path.write_text(f"#!/bin/sh\n{hook_body}\n", encoding="utf-8")
    refusing_hook_path.chmod(0o755)
    return refusing_hook_path


def hand_restack_level_2(sandbox: StackSandbox, merged_head_sha: str, merge_commit_sha: str) -> str:
    run_git(sandbox.developer_path, "checkout", "-q", "-B", "hand-level-2", "level-2")
    run_git(sandbox.developer_path, "rebase", "-q", "--onto", merge_commit_sha, merged_head_sha)
    commit_file(sandbox.developer_path, "hand.txt", "hand\n", "restacked by hand")
    return run_git(sandbox.developer_path, "rev-parse", "HEAD")


def pull_by_number(sandbox: StackSandbox, number: int) -> dict:
    return next(each for each in sandbox.read_stub_state()["pulls"] if each["number"] == number)


def manual_command_lines(comment_body: str) -> list[list[str]]:
    return [
        shlex.split(each_line)
        for each_line in comment_body.split("```bash\n", 1)[1].split("```", 1)[0].splitlines()
    ]


def test_should_leave_a_level_restacked_during_its_refused_push_and_follow_its_children(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    hand_sha = hand_restack_level_2(sandbox, merged_head_sha, merge_commit_sha)
    sandbox.all_pulls[0]["base"] = "level-1"
    sandbox.all_pulls[0]["pushDuringBaseEdit"] = [
        "git", "-C", str(sandbox.developer_path), "push", "-q", "--force", "origin",
        f"{hand_sha}:refs/heads/level-2",
    ]
    sandbox.write_stub_state()

    all_outcomes = run_restack_for_outcomes(sandbox, merged_head_sha, merge_commit_sha)

    assert all_outcomes[2] is restack_after_merge.RestackOutcome.ALREADY_RESTACKED
    assert sandbox.origin_head("level-2") == hand_sha
    assert pull_by_number(sandbox, 2)["base"] == "main"
    assert sandbox.read_stub_state()["comments"] == {}
    assert all_outcomes[3] is restack_after_merge.RestackOutcome.RESTACKED
    assert sandbox.subjects_above(hand_sha, "level-3") == ["level 3 work"]


def test_should_restore_the_base_it_set_when_the_push_is_refused(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.all_pulls[0]["base"] = "level-1"
    sandbox.write_stub_state()
    install_refusing_hook(sandbox, "exit 1")

    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert pull_by_number(sandbox, 2)["base"] == "level-1"
    assert NEEDS_REBASE_LABEL in pull_by_number(sandbox, 2)["labels"]
    assert len(sandbox.read_stub_state()["comments"]["2"]) == 1


def test_should_keep_a_base_changed_by_someone_else_when_the_push_is_refused(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.all_pulls[0]["base"] = "level-1"
    sandbox.write_stub_state()
    move_base_source = (
        "import json, os; p = os.environ['STUB_GH_STATE']; s = json.load(open(p)); "
        "s['pulls'][0]['base'] = 'integration'; json.dump(s, open(p, 'w'))"
    )
    install_refusing_hook(
        sandbox, f"{shlex.quote(sys.executable)} -c {shlex.quote(move_base_source)}\nexit 1"
    )

    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert pull_by_number(sandbox, 2)["base"] == "integration"
    assert len(sandbox.read_stub_state()["comments"]["2"]) == 1


def test_should_reach_the_grandchildren_when_run_again_after_a_partial_failure(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    refusing_hook_path = install_refusing_hook(
        sandbox,
        'while read old new ref; do [ "$ref" = refs/heads/level-3 ] && exit 1; done\nexit 0',
    )
    sandbox.run_restack(merged_head_sha, merge_commit_sha)
    level_3_head_after_first_run = sandbox.origin_head("level-3")
    refusing_hook_path.unlink()

    assert sandbox.run_restack(merged_head_sha, merge_commit_sha) == 0

    assert sandbox.origin_head("level-3") != level_3_head_after_first_run
    assert sandbox.subjects_above(sandbox.origin_head("level-2"), "level-3") == ["level 3 work"]
    assert NEEDS_REBASE_LABEL not in pull_by_number(sandbox, 3).get("labels", [])


def test_should_retarget_and_unlabel_a_level_restacked_by_hand(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    hand_sha = hand_restack_level_2(sandbox, merged_head_sha, merge_commit_sha)
    run_git(sandbox.developer_path, "push", "-q", "--force", "origin", f"{hand_sha}:refs/heads/level-2")
    sandbox.all_pulls[0]["base"] = "level-1"
    sandbox.all_pulls[0]["labels"] = [NEEDS_REBASE_LABEL]
    sandbox.write_stub_state()

    all_outcomes = run_restack_for_outcomes(sandbox, merged_head_sha, merge_commit_sha)

    assert all_outcomes[2] is restack_after_merge.RestackOutcome.ALREADY_RESTACKED
    assert sandbox.origin_head("level-2") == hand_sha
    assert pull_by_number(sandbox, 2)["base"] == "main"
    assert pull_by_number(sandbox, 2)["labels"] == []


def test_should_put_the_base_retarget_in_the_manual_commands(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    install_refusing_hook(sandbox, "exit 1")

    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert ["gh", "pr", "edit", "2", "--repo", REPOSITORY, "--base", "main"] in manual_command_lines(
        sandbox.read_stub_state()["comments"]["2"][0]
    )


def test_should_leave_the_instructions_when_the_label_cannot_be_added(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    sandbox.branch("unrelated", "main")
    commit_file(sandbox.developer_path, "other.txt", "other\n", "unrelated work")
    sandbox.push_branch("unrelated")
    sandbox.open_pull(8, "unrelated", "level-1")
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    stub_state = sandbox.read_stub_state()
    stub_state["failingEdits"] = ["8"]
    sandbox.state_path.write_text(json.dumps(stub_state), encoding="utf-8")

    assert sandbox.run_restack(merged_head_sha, merge_commit_sha) == 1

    all_level_8_comments = sandbox.read_stub_state()["comments"].get("8", [])
    assert len(all_level_8_comments) == 1
    assert all_level_8_comments[0].startswith(
        RESTACK_COMMENT_MARKER_TEMPLATE % MERGED_PULL_REQUEST_NUMBER
    )


def test_should_count_a_rebase_that_fails_without_a_conflict_as_a_step_failure(
    sandbox: StackSandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    level_2_head_before = sandbox.origin_head("level-2")
    run_git(sandbox.root_path, "clone", "-q", str(sandbox.origin_path), str(sandbox.runner_path))
    (sandbox.runner_path / "shared.txt").write_text("uncommitted edit\n", encoding="utf-8")

    exit_code = sandbox.run_restack(merged_head_sha, merge_commit_sha)

    assert exit_code == 1
    assert sandbox.origin_head("level-2") == level_2_head_before
    assert sandbox.read_stub_state()["comments"] == {}
    assert "#2" in capsys.readouterr().err


def test_should_name_each_cause_of_a_refused_push_in_the_comment(
    sandbox: StackSandbox,
) -> None:
    build_three_level_stack(sandbox)
    merged_head_sha, merge_commit_sha = sandbox.squash_merge(
        MERGED_PULL_REQUEST_NUMBER, "level-1"
    )
    sandbox.write_stub_state()
    install_refusing_hook(sandbox, "exit 1")

    sandbox.run_restack(merged_head_sha, merge_commit_sha)

    comment_body = sandbox.read_stub_state()["comments"]["2"][0]
    for each_cause in ("lease", "branch rule", "workflow file", "workflows permission"):
        assert each_cause in comment_body
