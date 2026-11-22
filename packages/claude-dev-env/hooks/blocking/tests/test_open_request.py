"""Behavioral tests for reading a pull request open from a PreToolUse payload.

gh pr create --repo acme/tools --title "--head evil" -> acme/tools, quoted option ignored
mcp create_pull_request {owner, repo, head}          -> acme/tools, head listed by GitHub
mcp create_pull_request {owner, repo, head: u:b}     -> acme/tools, head listed for u
gh pr merge 12                                       -> no open
gh pr create --head a && cd x && gh pr create        -> two opens, each with its own folder
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from blocking.gate_run_reads import ReadSlice
from blocking.merge_review_gate_parts import open_request
from blocking.merge_review_gate_parts.open_request import (
    OpenRequest,
    ShellOpenCall,
    base_tip,
    first_parent_ancestors,
    is_held_by_another_line,
    is_outside_base,
    open_calls_from,
    open_request_for,
)


def _only_request(all_payload_fields: dict[str, object]) -> OpenRequest:
    [only_call] = open_calls_from(all_payload_fields)
    return open_request_for(only_call)


def _shell_payload(command: str, folder: Path) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(folder)}


def _create_payload(head: str, folder: Path, owner: str = "acme") -> dict[str, object]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": owner, "repo": "tools", "head": head},
        "cwd": str(folder),
    }


def _git(folder: Path, *all_arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(folder), *all_arguments], capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def _commit(folder: Path, message: str) -> str:
    _git(
        folder,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        message,
    )
    return _git(folder, "rev-parse", "HEAD")


def _checkout_on(tmp_path: Path, branch: str) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "--quiet", "--initial-branch", branch)
    return checkout


def _bare_remote(github: Path, owner: str) -> Path:
    remote = github / owner / "tools.git"
    remote.mkdir(parents=True)
    _git(remote, "init", "--quiet", "--bare")
    return remote


def _redirect_github(monkeypatch: pytest.MonkeyPatch, github: Path) -> None:
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{github}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/")


def test_should_read_the_repository_and_ignore_options_quoted_in_the_title(tmp_path: Path) -> None:
    payload = _shell_payload('gh pr create --repo acme/tools --title "--head evil"', tmp_path)
    assert _only_request(payload) == OpenRequest(owner="acme", repo="tools", head=None)


def test_should_read_the_create_tool_with_no_head_branch(tmp_path: Path) -> None:
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools"},
        "cwd": str(tmp_path),
    }
    assert _only_request(payload) == OpenRequest(owner="acme", repo="tools", head=None)


def test_should_read_a_pushed_branch_from_outside_any_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    _redirect_github(monkeypatch, github)
    assert _only_request(_create_payload("feature", tmp_path)) == OpenRequest(
        owner="acme", repo="tools", head=head
    )


def test_should_read_a_fork_branch_from_the_fork_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    base_head = _commit(checkout, "base")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    fork_head = _commit(checkout, "fork")
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "someone")), "feature")
    _redirect_github(monkeypatch, github)
    assert base_head != fork_head
    assert _only_request(_create_payload("someone:feature", tmp_path)).head == fork_head


def test_should_read_no_head_for_a_branch_the_repository_does_not_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    github = tmp_path / "github.com"
    _bare_remote(github, "acme")
    _redirect_github(monkeypatch, github)
    assert _only_request(_create_payload("feature", tmp_path)).head is None


def test_should_list_in_an_empty_folder_so_the_checkout_config_never_applies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    github = tmp_path / "github.com"
    _git(checkout, "push", "--quiet", str(_bare_remote(github, "acme")), "feature")
    _redirect_github(monkeypatch, github)
    decoy = tmp_path / "decoy"
    _commit(checkout, "decoy")
    _git(checkout, "push", "--quiet", str(_bare_remote(decoy, "acme")), "feature")
    _git(checkout, "config", f"url.{decoy}/acme/.insteadOf", "https://github.com/acme/")
    monkeypatch.chdir(checkout)
    assert _only_request(_create_payload("feature", tmp_path)).head == head


def _listing_answered_by(
    monkeypatch: pytest.MonkeyPatch,
    answer: Callable[[list[str], Mapping[str, str] | None], str | None],
) -> None:
    run_before_patch = open_request.child_stdout

    def answer_the_listing(
        all_command_words: Sequence[str],
        own_timeout_seconds: float,
        read_slice: ReadSlice,
        working_directory: str | None = None,
        all_environment_variables: Mapping[str, str] | None = None,
    ) -> str | None:
        if "ls-remote" in all_command_words:
            return answer(list(all_command_words), all_environment_variables)
        return run_before_patch(
            all_command_words, own_timeout_seconds, read_slice, working_directory, all_environment_variables
        )

    monkeypatch.setattr(open_request, "child_stdout", answer_the_listing)


def test_should_read_no_head_when_the_listing_gives_no_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _listing_answered_by(monkeypatch, lambda _all_words, _environment: None)
    assert _only_request(_create_payload("feature", tmp_path)).head is None


def test_should_run_the_listing_without_a_terminal_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)
    monkeypatch.delenv("GCM_INTERACTIVE", raising=False)
    all_seen_environments: list[Mapping[str, str] | None] = []

    def record_environment(
        _all_words: list[str], all_environment_variables: Mapping[str, str] | None
    ) -> str | None:
        all_seen_environments.append(all_environment_variables)
        return None

    _listing_answered_by(monkeypatch, record_environment)
    _only_request(_create_payload("feature", tmp_path))
    [all_environment_variables] = all_seen_environments
    assert all_environment_variables is not None
    assert all_environment_variables["GIT_TERMINAL_PROMPT"] == "0"
    assert all_environment_variables["GCM_INTERACTIVE"] == "never"


def test_should_pick_the_listed_line_that_names_the_branch_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = f"{'1' * 40}\trefs/heads/feature-two\n{'2' * 40}\trefs/heads/feature\n"
    _listing_answered_by(monkeypatch, lambda _all_words, _environment: listing)
    assert _only_request(_create_payload("feature", tmp_path)).head == "2" * 40


def test_should_run_no_listing_for_a_call_that_names_no_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    all_commands: list[list[str]] = []

    def record_command(all_words: list[str], _environment: Mapping[str, str] | None) -> None:
        all_commands.append(all_words)

    _listing_answered_by(monkeypatch, record_command)
    assert _only_request(_create_payload("feature", tmp_path, owner="")).head is None
    assert all_commands == []


def test_should_read_the_checkout_branch_when_github_lists_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    github = tmp_path / "github.com"
    _bare_remote(github, "acme")
    _redirect_github(monkeypatch, github)
    assert _only_request(_create_payload("feature", checkout)).head == head


def test_should_read_a_fork_branch_from_the_checkout_when_github_lists_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    github = tmp_path / "github.com"
    _bare_remote(github, "someone")
    _redirect_github(monkeypatch, github)
    assert _only_request(_create_payload("someone:feature", checkout)).head == head


def test_should_read_a_shell_open_branch_from_the_checkout(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    head = _commit(checkout, "first")
    payload = _shell_payload("gh pr create --repo acme/tools --head feature", checkout)
    assert _only_request(payload) == OpenRequest(owner="acme", repo="tools", head=head)


def test_should_read_the_checkout_branch_for_a_shell_open_that_names_no_head(
    tmp_path: Path,
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    _commit(checkout, "first")
    payload = _shell_payload("gh pr create --repo acme/tools", checkout)
    assert _only_request(payload).branch == "feature"


def test_should_read_the_branch_a_fork_head_names_without_its_owner(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "main")
    _commit(checkout, "first")
    payload = _shell_payload("gh pr create --repo acme/tools --head user:feature", checkout)
    assert _only_request(payload).branch == "feature"


def test_should_list_the_first_parent_commits_before_a_head_newest_first(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    first = _commit(checkout, "first")
    second = _commit(checkout, "second")
    head = _commit(checkout, "third")
    assert first_parent_ancestors(head, str(checkout)) == (second, first)


def test_should_list_no_commits_before_a_head_the_folder_cannot_read(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    _commit(checkout, "first")
    assert first_parent_ancestors("1" * 40, str(checkout)) == ()


def test_should_find_a_commit_another_branch_holds_without_the_head(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    reviewed = _commit(checkout, "reviewed")
    _git(checkout, "checkout", "--quiet", "-b", "second")
    head = _commit(checkout, "second work")
    assert is_held_by_another_line(reviewed, head, str(checkout)) is True


def test_should_not_count_the_branch_that_holds_both_the_commit_and_the_head(
    tmp_path: Path,
) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    reviewed = _commit(checkout, "reviewed")
    head = _commit(checkout, "fix")
    assert is_held_by_another_line(reviewed, head, str(checkout)) is False


def test_should_count_a_commit_as_held_by_another_line_when_the_branch_read_fails(
    tmp_path: Path,
) -> None:
    not_a_checkout = tmp_path / "plain folder"
    not_a_checkout.mkdir()
    assert is_held_by_another_line("1" * 40, "2" * 40, str(not_a_checkout)) is True


def test_should_read_the_first_parents_git_stores_and_not_a_replace_graft(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    reviewed = _commit(checkout, "reviewed")
    _git(checkout, "checkout", "--quiet", "--orphan", "unrelated")
    head = _commit(checkout, "unrelated work")
    _git(checkout, "replace", "--graft", head, reviewed)
    assert reviewed not in first_parent_ancestors(head, str(checkout))
    assert is_held_by_another_line(reviewed, head, str(checkout)) is True


def test_should_read_the_first_parents_git_stores_and_not_a_grafts_file(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    reviewed = _commit(checkout, "reviewed")
    _git(checkout, "checkout", "--quiet", "--orphan", "unrelated")
    head = _commit(checkout, "unrelated work")
    (checkout / ".git" / "info").mkdir(exist_ok=True)
    (checkout / ".git" / "info" / "grafts").write_text(f"{head} {reviewed}\n", encoding="utf-8")
    assert reviewed not in first_parent_ancestors(head, str(checkout))
    assert is_held_by_another_line(reviewed, head, str(checkout)) is True


def test_should_read_the_base_a_shell_open_names(tmp_path: Path) -> None:
    payload = _shell_payload("gh pr create --repo acme/tools --base release -H feature", tmp_path)
    assert {open_request_for(each_call).base for each_call in open_calls_from(payload)} == {
        "release"
    }


def test_should_read_no_base_for_a_shell_open_that_names_none(tmp_path: Path) -> None:
    payload = _shell_payload("gh pr create --repo acme/tools -H feature", tmp_path)
    assert {open_request_for(each_call).base for each_call in open_calls_from(payload)} == {None}


def test_should_read_the_base_the_create_tool_names(tmp_path: Path) -> None:
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools", "base": "release"},
        "cwd": str(tmp_path),
    }
    assert _only_request(payload).base == "release"


def test_should_read_the_gh_merge_base_of_the_head_branch_when_no_base_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, _main_commit, release_commit = _pushed_base(tmp_path, monkeypatch)
    _git(checkout, "config", "branch.release.gh-merge-base", "release")
    _git(checkout, "config", "branch.feature.gh-merge-base", "release")
    _git(checkout, "config", "branch.main.gh-merge-base", "wrong")
    for each_command in ("gh pr create --repo acme/tools", "gh pr create --repo acme/tools -H u:feature"):
        all_calls = open_calls_from(_shell_payload(each_command, checkout))
        assert {base_tip(open_request_for(each_call)) for each_call in all_calls} == {release_commit}


def test_should_give_no_base_when_the_gh_merge_base_read_gives_no_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout, main_commit, _release_commit = _pushed_base(tmp_path, monkeypatch)
    payload = _shell_payload("gh pr create --repo acme/tools -H release", checkout)
    assert {base_tip(open_request_for(each_call)) for each_call in open_calls_from(payload)} == {
        main_commit
    }

    def refuse_the_config_read(*all_arguments: object, **all_keywords: object) -> str | None:
        all_command_words = all_arguments[0]
        assert isinstance(all_command_words, list)
        if "config" in all_command_words:
            return None
        return original_child_stdout(*all_arguments, **all_keywords)

    original_child_stdout = open_request.child_stdout
    monkeypatch.setattr(open_request, "child_stdout", refuse_the_config_read)
    assert [base_tip(open_request_for(each_call)) for each_call in open_calls_from(payload)] == [None]


def test_should_give_no_base_for_a_create_tool_call_that_names_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pushed_base(tmp_path, monkeypatch)
    payload = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "acme", "repo": "tools", "head": "feature"},
        "cwd": str(tmp_path),
    }
    assert base_tip(_only_request(payload)) is None


@pytest.mark.parametrize(
    ("command", "base"),
    [
        ("gh pr create --repo acme/tools -H feature --base=one --base two -Bthree", "three"),
        ("gh pr create --repo acme/tools -H feature -B=one", "one"),
    ],
)
def test_should_read_the_last_base_gh_reads(tmp_path: Path, command: str, base: str) -> None:
    payload = _shell_payload(command, tmp_path)
    assert {open_request_for(each_call).base for each_call in open_calls_from(payload)} == {base}


def test_should_give_no_base_when_the_last_base_is_empty_and_the_pattern_reading_saw_an_earlier_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pushed_base(tmp_path, monkeypatch)
    payload = _shell_payload('gh pr create --repo acme/tools -H release --base release --base ""', tmp_path)
    all_requests = [open_request_for(each_call) for each_call in open_calls_from(payload)]
    assert all(each_request.base != "release" or base_tip(each_request) is None for each_request in all_requests)


def _pushed_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, str]:
    checkout = _checkout_on(tmp_path, "main")
    main_commit = _commit(checkout, "main work")
    _git(checkout, "checkout", "--quiet", "-b", "release")
    release_commit = _commit(checkout, "release work")
    github = tmp_path / "github.com"
    remote = _bare_remote(github, "acme")
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(checkout, "push", "--quiet", str(remote), "main", "release")
    _redirect_github(monkeypatch, github)
    return checkout, main_commit, release_commit


def test_should_read_the_named_base_from_github(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _checkout, _main_commit, release_commit = _pushed_base(tmp_path, monkeypatch)
    request = OpenRequest(owner="acme", repo="tools", head=None, base="release")
    assert base_tip(request) == release_commit


def test_should_read_the_default_branch_from_github_when_no_base_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _checkout, main_commit, _release_commit = _pushed_base(tmp_path, monkeypatch)
    assert base_tip(OpenRequest(owner="acme", repo="tools", head=None)) == main_commit


def test_should_read_no_base_commit_for_a_base_github_does_not_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pushed_base(tmp_path, monkeypatch)
    request = OpenRequest(owner="acme", repo="tools", head=None, base="missing")
    assert base_tip(request) is None


def test_should_find_a_branch_commit_outside_the_base_below_it(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "main")
    base_commit = _commit(checkout, "base")
    _git(checkout, "checkout", "--quiet", "-b", "feature")
    reviewed = _commit(checkout, "reviewed")
    assert is_outside_base(reviewed, base_commit, str(checkout)) is True


def test_should_count_a_commit_the_base_holds_as_inside_the_base(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "main")
    reviewed = _commit(checkout, "reviewed")
    base_commit = _commit(checkout, "base moved on")
    assert is_outside_base(reviewed, base_commit, str(checkout)) is False
    assert is_outside_base(reviewed, reviewed, str(checkout)) is False


def test_should_count_a_commit_as_inside_a_base_the_folder_cannot_read(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "feature")
    reviewed = _commit(checkout, "reviewed")
    assert is_outside_base(reviewed, "1" * 40, str(checkout)) is False


def test_should_read_no_open_from_a_merge_command(tmp_path: Path) -> None:
    assert open_calls_from(_shell_payload("gh pr merge 12", tmp_path)) == []


def test_should_read_every_chained_create_with_its_own_repository_head_and_folder(
    tmp_path: Path,
) -> None:
    other = tmp_path / "other"
    command = (
        "gh pr create --repo acme/tools --head one --fill && "
        "cd other && python scripts/pull_request.py create --head two; "
        "cd nested && gh pr create -R someone/fork --fill"
    )
    assert open_calls_from(_shell_payload(command, tmp_path)) == [
        ShellOpenCall(repository=("acme", "tools"), branch="one", folder=str(tmp_path)),
        ShellOpenCall(repository=None, branch="two", folder=str(other)),
        ShellOpenCall(repository=("someone", "fork"), branch="HEAD", folder=str(other / "nested")),
    ]


def test_should_read_creates_on_separate_lines_as_separate_opens(tmp_path: Path) -> None:
    command = (
        "python scripts/pull_request.py create --repo acme/tools\n"
        "gh pr create --repo acme/tools --head two"
    )
    assert [
        each_call.branch for each_call in open_calls_from(_shell_payload(command, tmp_path))
    ] == ["HEAD", "two"]


def test_should_keep_a_head_on_a_continued_line_with_its_create(tmp_path: Path) -> None:
    command = "gh pr create --repo acme/tools \\\n  --head one --fill"
    assert open_calls_from(_shell_payload(command, tmp_path)) == [
        ShellOpenCall(repository=("acme", "tools"), branch="one", folder=str(tmp_path)),
    ]


def test_should_read_the_head_of_each_chained_create(tmp_path: Path) -> None:
    checkout = _checkout_on(tmp_path, "one")
    first_head = _commit(checkout, "first")
    _git(checkout, "checkout", "--quiet", "-b", "two")
    second_head = _commit(checkout, "second")
    command = (
        "gh pr create --repo acme/tools --head one && gh pr create --repo acme/tools --head two"
    )
    all_requests = [
        open_request_for(each_call)
        for each_call in open_calls_from(_shell_payload(command, checkout))
    ]
    assert [each_request.head for each_request in all_requests] == [first_head, second_head]


MAIN_FLOOR_START = "/work/main"
ALL_MAIN_FLOOR_READINGS = [
    ("cat <<'BODY' | bash\ngh pr create --head two\nBODY", None, "two", "/work/main"),
    ("cat > x.sh <<'BODY'\ngh pr create --head two\nBODY\nbash x.sh", None, "two", "/work/main"),
    (". /dev/stdin <<'BODY'\ngh pr create --head two\nBODY", None, "two", "/work/main"),
    ("eval \"$(cat <<'BODY'\ngh pr create --head two\nBODY\n)\"", None, "two", "/work/main"),
    ("echo gh pr create --head two | bash; x=`gh pr create --head one`", None, "two", "/work/main"),
    (
        "echo gh pr create --head two | bash; bash -c 'gh pr create --head one'",
        None,
        "two",
        "/work/main",
    ),
    (
        "echo gh pr create --head two | bash; eval 'gh pr create --head one'",
        None,
        "two",
        "/work/main",
    ),
    ("{ cd ../rsub; } | true; gh pr create --fill", None, "HEAD", "/work/main"),
    ('gh pr create --head one --label "see gh pr create"', None, "one", "/work/main"),
    ('gh pr create --head one --label "a; gh pr create --head two"', None, "one", "/work/main"),
    ('gh pr create --head one --label "a && gh pr create --head two"', None, "one", "/work/main"),
    ('gh pr create --head one --label "a | gh pr create --head two"', None, "one", "/work/main"),
    ('gh pr create --head one --label "a\ngh pr create --head two"', None, "one", "/work/main"),
    (
        'gh pr create --fill --label "see gh pr create --repo acme/tools --head two"',
        ("acme", "tools"),
        "two",
        "/work/main",
    ),
    (
        'gh pr create --fill --label "a; gh pr create --repo acme/tools --head two"',
        None,
        "HEAD",
        "/work/main",
    ),
    (
        'gh pr create --head one --label "see pull_request.py create --head two"',
        None,
        "one",
        "/work/main",
    ),
    ("gh pr create --head one --label 'a; gh pr create --head two'", None, "one", "/work/main"),
    ("gh pr create --fill", None, "HEAD", "/work/main"),
    ("gh pr create --head two", None, "two", "/work/main"),
    ("gh pr create --head=two", None, "two", "/work/main"),
    ("gh pr create -H two", None, "two", "/work/main"),
    ("gh pr create -Htwo", None, "HEAD", "/work/main"),
    ("gh pr create --head one --head two", None, "one", "/work/main"),
    ("gh pr create --repo acme/tools --head two", ("acme", "tools"), "two", "/work/main"),
    ("gh pr create -R acme/tools --head two", ("acme", "tools"), "two", "/work/main"),
    ("gh pr create --repo=acme/tools --head two", ("acme", "tools"), "two", "/work/main"),
    ("cd ../rsub && gh pr create --fill", None, "HEAD", "/work/main/../rsub"),
    ("cd ../rsub; gh pr create --head two", None, "two", "/work/main/../rsub"),
    ("cd /abs/place && gh pr create --fill", None, "HEAD", "/abs/place"),
    ('cd "../with space" && gh pr create --fill', None, "HEAD", "/work/main/../with space"),
    ("pushd ../rsub && gh pr create --fill", None, "HEAD", "/work/main/../rsub"),
    ("Set-Location ../rsub; gh pr create --fill", None, "HEAD", "/work/main/../rsub"),
    (
        "(cd ../rsub && gh pr create --fill) ; gh pr create --fill",
        None,
        "HEAD",
        "/work/main/../rsub",
    ),
    ("cd ../a && cd ../b && gh pr create --fill", None, "HEAD", "/work/main/../b"),
    ("gh pr create --head one && cd ../rsub && gh pr create --head two", None, "one", "/work/main"),
    ("gh pr create --head one ; gh pr create --head two", None, "one", "/work/main"),
    ("gh pr create --head one || gh pr create --head two", None, "one", "/work/main"),
    ("gh pr create --head one\ngh pr create --head two", None, "one", "/work/main"),
    ("python3 scripts/pull_request.py create --head two", None, "two", "/work/main"),
    (
        "python3 scripts/pull_request.py create --repo acme/tools --head two",
        ("acme", "tools"),
        "two",
        "/work/main",
    ),
    ("cd ../rsub && python3 scripts/pull_request.py create", None, "HEAD", "/work/main/../rsub"),
    ("gh pr create --title 'cd ../evil' --head two", None, "two", "/work/main"),
    ("gh pr create --body 'x' --head two", None, "two", "/work/main"),
    (
        'gh pr create --title "--head evil" --repo acme/tools',
        ("acme", "tools"),
        "HEAD",
        "/work/main",
    ),
    ("bash -c 'cd ../rsub && gh pr create --fill'", None, "HEAD", "/work/main"),
    ("echo gh pr create --head two | bash", None, "two", "/work/main"),
    ("bash <<'EOF'\ngh pr create --head two\nEOF", None, "two", "/work/main"),
    ("export GH_REPO=other/thing; gh pr create --head two", None, "two", "/work/main"),
    ("GH_REPO=other/thing gh pr create --head two", None, "two", "/work/main"),
    ("GH_REPO=other/thing env -u GH_REPO gh pr create --head two", None, "two", "/work/main"),
    ("GH_REPO=other/thing env -i gh pr create --head two", None, "two", "/work/main"),
    ("git commit -m 'x; gh pr create --head two'", None, "two", "/work/main"),
    ("gh.exe pr create --head two", None, "two", "/work/main"),
    ("cd $WORK && gh pr create --fill", None, "HEAD", "/work/main/$WORK"),
    ("cd - && gh pr create --fill", None, "HEAD", "/work/main/-"),
    ("x=$(gh pr create --head two)", None, "two)", "/work/main"),
    ("gh pr create --head 'two'", None, "two", "/work/main"),
    ('gh pr create --head "two"', None, "two", "/work/main"),
    ("gh pr create --head user:two", None, "user:two", "/work/main"),
]


@pytest.mark.parametrize(("command", "repository", "branch", "folder"), ALL_MAIN_FLOOR_READINGS)
def test_should_keep_the_first_create_reading_main_gave_as_one_of_its_calls(
    command: str, repository: tuple[str, str] | None, branch: str, folder: str
) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": MAIN_FLOOR_START}
    assert ShellOpenCall(repository=repository, branch=branch, folder=folder) in open_calls_from(
        payload
    )


def _branches(command: str) -> set[str]:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": MAIN_FLOOR_START}
    return {each_call.branch for each_call in open_calls_from(payload)}


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create -Htwo",
        "gh pr create -H=two",
        "gh pr create --head one --head two",
        "gh pr create -H one --head=two",
        "gh pr create --head=one -Htwo",
        "gh pr create --fill; gh pr create --head one -H two",
    ],
)
def test_should_check_every_head_a_create_names(command: str) -> None:
    assert "two" in _branches(command)


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create -dHtwo",
        "gh pr create -dH two",
        "gh pr create -fH=two",
        "gh pr create --head one -dHtwo",
        "gh -R o/r pr create -wdHtwo --fill",
    ],
)
def test_should_check_the_head_a_short_flag_cluster_names(command: str) -> None:
    assert "two" in _branches(command)


def test_should_read_the_rest_of_a_cluster_after_the_head_letter_as_the_head() -> None:
    all_branches = _branches("gh pr create -Hdtwo")
    assert "dtwo" in all_branches
    assert "two" not in all_branches


def test_should_read_each_named_head_as_its_own_call() -> None:
    assert _branches("python3 scripts/pull_request.py create --head one -Htwo --head=three") == {
        "one",
        "two",
        "three",
    }


@pytest.mark.parametrize(
    "command",
    [
        "bash <<<'gh pr create --head two'",
        "G=gh; $G pr create --head two",
        "alias g=gh; g pr create --head two",
        "bash make_pull_request.sh --head two",
    ],
)
def test_should_not_read_a_create_only_a_shell_input_variable_or_alias_holds(command: str) -> None:
    assert "two" not in _branches(command)


def test_should_leave_unfollowed_a_create_with_no_repository_after_an_export_of_gh_repo() -> None:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "export GH_REPO=other/thing; gh pr create --head two"},
        "cwd": MAIN_FLOOR_START,
    }
    all_calls = open_calls_from(payload)
    assert {each_call.repository for each_call in all_calls} == {None}
    assert False in {getattr(each_call, "is_folder_followed", True) for each_call in all_calls}


def _repositories(command: str) -> set[tuple[str, str] | None]:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": MAIN_FLOOR_START}
    return {each_call.repository for each_call in open_calls_from(payload)}


@pytest.mark.parametrize(
    ("command", "all_expected_repositories"),
    [
        ("gh -R o/r pr create -R acme/tools --repo=a/b --repo=a/b", {("a", "b")}),
        ("gh -R a/b pr create --repo acme/tools", {("acme", "tools")}),
        ("gh -R a/b pr create --fill", {("a", "b")}),
        ("gh pr create --repo acme/tools -dRa/b", {("a", "b"), ("acme", "tools")}),
        ("gh pr create --repo acme/tools -R=a/b", {("a", "b"), ("acme", "tools")}),
        ("gh pr create --repo a/b --title --repo=acme/tools", {("a", "b")}),
        ("GH_REPO=acme/tools gh pr create -R a/b", {("a", "b")}),
        ("x & eval \"\"gh\" -R acme/tools pr create --repo=a/b ''\"\" ~\"", {("a", "b")}),
        ("python3 scripts/pull_request.py create --repo acme/tools --repo a/b", {("a", "b"), ("acme", "tools")}),
    ],
)
def test_should_read_the_repository_the_last_repository_flag_names(
    command: str, all_expected_repositories: set[tuple[str, str] | None]
) -> None:
    assert _repositories(command) == all_expected_repositories


@pytest.mark.parametrize("separator", [";", "&&", "||", "|", "\n"])
def test_should_read_create_words_after_a_separator_inside_a_quoted_value(separator: str) -> None:
    assert "two" in _branches(f"git commit -m 'x{separator} gh pr create --head two'")


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --head one; git commit -m 'x; gh pr create --head two'",
        "gh pr create --head one --label 'a && gh pr create --head two'",
        "gh pr create --head one; git commit -m 'x\ngh pr create --head two'",
        'gh pr create --head one --body "a\ngh pr create --head two"',
    ],
)
def test_should_not_read_a_later_quoted_create(command: str) -> None:
    assert "two" not in _branches(command)


@pytest.mark.parametrize(
    "command",
    [
        "GH_REPO=other/thing env -u GH_REPO gh pr create --head two",
        "gh pr create --repo other/thing --head two ; GH_REPO=other/thing env -u GH_REPO gh pr create --head two",
        "gh pr create --repo other/thing --head two && GH_REPO=other/thing gh pr create --head two",
    ],
)
def test_should_add_an_origin_call_for_every_create_a_gh_repo_prefix_names(command: str) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": MAIN_FLOOR_START}
    all_calls = open_calls_from(payload)
    assert ShellOpenCall(repository=("other", "thing"), branch="two", folder=MAIN_FLOOR_START) in all_calls
    assert ShellOpenCall(repository=None, branch="two", folder=MAIN_FLOOR_START) in all_calls


def test_should_add_no_origin_call_for_a_create_that_names_its_own_repository() -> None:
    command = "GH_REPO=a/b gh pr create --repo other/thing --head two"
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": MAIN_FLOOR_START}
    assert {each_call.repository for each_call in open_calls_from(payload)} == {("other", "thing")}
