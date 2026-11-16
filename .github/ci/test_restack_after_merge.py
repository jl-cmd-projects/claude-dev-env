"""Specifications for restacking open stack levels after a lower level squash-merges.

Each scenario builds a bare origin and two clones in a temporary directory, merges
level 1 into main by squash the way the merge queue does, deletes its branch, and
runs the script from a fresh clone with a stub `gh` on PATH that records each call.
"""

import json
import os
import stat
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_CI_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_CI_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_SCRIPTS_DIR))

import restack_after_merge

from config.restack_after_merge_constants import (
    NEEDS_REBASE_LABEL,
    RESTACK_COMMENT_MARKER_TEMPLATE,
)

REPOSITORY = "example-owner/example-repo"
MERGED_PULL_REQUEST_NUMBER = 1

STUB_GH_SOURCE = textwrap.dedent(
    """
    import json, os, subprocess, sys
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
                          "isCrossRepository": each.get("cross", False), "timelineItems": {"nodes": events}})
        print(json.dumps({"data": {"repository": {"pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}))
    elif all_arguments[0] == "api" and all_arguments[-2] == "--jq":
        number = all_arguments[2].split("/")[-2]
        print("\\n".join(state["comments"].get(number, [])))
    elif all_arguments[:2] == ["pr", "edit"]:
        pull = next(each for each in state["pulls"] if str(each["number"]) == all_arguments[2])
        if "--base" in all_arguments:
            pull["previousBase"], pull["base"] = pull["base"], option("--base")
            if pull.get("pushDuringBaseEdit"):
                subprocess.run(pull.pop("pushDuringBaseEdit"), check=True)
        if "--add-label" in all_arguments:
            pull["labels"] = sorted(set(pull.get("labels", [])) | {option("--add-label")})
        save()
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

    def squash_merge(self, number: int, branch_name: str) -> tuple[str, str]:
        head_sha = self.push_branch(branch_name)
        run_git(
            self.developer_path,
            "push",
            "-q",
            "origin",
            f"{head_sha}:refs/pull/{number}/head",
        )
        run_git(self.developer_path, "checkout", "-q", "main")
        run_git(self.developer_path, "merge", "-q", "--squash", branch_name)
        run_git(
            self.developer_path,
            "commit",
            "-q",
            "-m",
            f"level {number} squashed (#{number})",
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
                ]
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
    sandbox.branch("level-1", "level-1~1")
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
    assert (
        f"--force-with-lease=level-2:{all_heads_before['level-2']}"
        in level_2_comments[0]
    )
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
    assert (
        "the force push with lease was rejected"
        in sandbox.read_stub_state()["comments"]["2"][0]
    )


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
        fork_pull_request, merged_pull_request, "origin"
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
        target, merged_pull_request, "abc123", "the rebase hit a conflict", "origin"
    )

    assert f"git rebase --onto origin/main {fork_sha}" in comment_body
    assert "git push --force-with-lease=level-2:abc123 origin level-2" in comment_body


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
        ]
    )

    assert (parsed_arguments.merged_pr, parsed_arguments.remote) == (7, "origin")


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
        REPOSITORY, merged_pull_request, "origin"
    )

    assert all_outcomes == [
        (2, restack_after_merge.RestackOutcome.RESTACKED),
        (3, restack_after_merge.RestackOutcome.RESTACKED),
    ]
