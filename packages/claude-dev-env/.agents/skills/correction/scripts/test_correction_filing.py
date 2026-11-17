"""Behavior tests for correction_filing with a stand-in gh and a stand-in post lint."""

from __future__ import annotations

import importlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

correction_filing = importlib.import_module("correction_filing")

STAND_IN_GH = r'''
import json, os, re, sys
store_path = os.environ["STAND_IN_GH_STORE"]
store = json.load(open(store_path, encoding="utf-8"))
arguments = sys.argv[2:]
method, fields, positional, index = "GET", {}, [], 0
while index < len(arguments):
    each = arguments[index]
    if each == "--method":
        method = arguments[index + 1]; index += 2
    elif each == "--jq":
        index += 2
    elif each == "-f":
        key, value = arguments[index + 1].split("=", 1); fields[key] = value; index += 2
    elif each == "--paginate":
        index += 1
    else:
        positional.append(each); index += 1
path = positional[0]
match = re.match(r"repos/([^/?]+/[^/?]+)(.*)", path)
repository, rest = match.group(1), match.group(2)
if repository not in store:
    sys.stderr.write("HTTP 404: Not Found (https://api.github.com/" + path + ")\n"); sys.exit(1)
repo = store[repository]
def save():
    json.dump(store, open(store_path, "w", encoding="utf-8"))
if rest == "" and method == "GET":
    print(json.dumps({"private": repo["private"], "has_issues": repo["has_issues"]}))
elif rest.startswith("/labels/") and method == "GET":
    if rest[len("/labels/"):] not in repo["labels"]:
        sys.stderr.write("HTTP 404: Not Found\n"); sys.exit(1)
    print(json.dumps({"name": rest[len("/labels/"):]}))
elif rest == "/labels" and method == "POST":
    repo["labels"].append(fields["name"]); save(); print(json.dumps({"name": fields["name"]}))
elif rest.startswith("/issues?") and method == "GET":
    query = dict(each.split("=", 1) for each in rest[len("/issues?"):].split("&"))
    for each_issue in repo["issues"]:
        if query["labels"] in each_issue["labels"] and query["state"] in ("all", each_issue["state"]):
            print(json.dumps({k: each_issue[k] for k in ("number", "title", "url", "body", "state")}))
elif rest == "/issues" and method == "POST":
    if not repo["has_issues"]:
        sys.stderr.write("HTTP 410: Issues are disabled for this repo\n"); sys.exit(1)
    number = len(repo["issues"]) + 1
    url = "https://github.com/%s/issues/%d" % (repository, number)
    repo["issues"].append({"number": number, "title": fields["title"], "url": url, "body": fields["body"],
                           "labels": [fields["labels[]"]], "state": "open"})
    save(); print(url)
elif re.match(r"/issues/\d+/comments$", rest) and method == "POST":
    number = int(rest.split("/")[2])
    url = "https://github.com/%s/issues/%d#issuecomment-%d" % (repository, number, len(repo["comments"]) + 1)
    repo["comments"].append({"issue": number, "body": fields["body"], "url": url})
    save(); print(url)
else:
    sys.stderr.write("stand-in gh has no route for %s %s\n" % (method, path)); sys.exit(1)
'''

STAND_IN_POST_LINT = r'''
import sys
arguments = sys.argv[1:]
body = open(arguments[arguments.index("--body-file") + 1], encoding="utf-8").read()
with open(__file__ + ".calls", "a", encoding="utf-8") as calls:
    calls.write(arguments[arguments.index("--action") + 1] + " " + arguments[arguments.index("--repository") + 1] + "\n")
if "LINT-REFUSES" in body:
    sys.stderr.write("line 3 frames a contrast\n")
    sys.exit(1)
'''

BRIEF = (
    "Correction: stop opening a pull request after a correction\n"
    "Asked: post a correction issue\n"
    "Agent did: built a hook and opened a pull request\n"
    "Corrected to: post an issue labelled correction\n"
    "Where: hooks/blocking/example.py\n"
    "Evidence: reply at 10:02 named the pull request\n"
    "Repeat: no\n"
    "Suggested layer: 2, a lint"
)


class FilingWorld:
    """The stand-in GitHub, the managed root, and the paths a test drives."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.store_path = tmp_path / "github.json"
        self.config_path = tmp_path / "correction-capture.json"
        self.managed_root = tmp_path / "managed"
        self.lint_path = self.managed_root / "scripts" / "durable_post_lint.py"
        self.store_path.write_text("{}", encoding="utf-8")

    def add_repository(self, repository: str, *, private: bool = True, has_issues: bool = True, labels: tuple[str, ...] = ()) -> None:
        store = self.github()
        store[repository] = {"private": private, "has_issues": has_issues, "labels": list(labels), "issues": [], "comments": []}
        self.store_path.write_text(json.dumps(store), encoding="utf-8")

    def github(self) -> dict[str, dict[str, object]]:
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def issues(self, repository: str) -> list[dict[str, object]]:
        return self.github()[repository]["issues"]

    def close_issue(self, repository: str, number: int) -> None:
        store = self.github()
        store[repository]["issues"][number - 1]["state"] = "closed"
        self.store_path.write_text(json.dumps(store), encoding="utf-8")

    def set_inbox(self, repository: str) -> None:
        self.config_path.write_text(json.dumps({"repository": repository, "label": "correction"}), encoding="utf-8")

    def lint_calls(self) -> list[str]:
        calls_path = Path(str(self.lint_path) + ".calls")
        return calls_path.read_text(encoding="utf-8").splitlines() if calls_path.exists() else []

    def checkout(self, origin_url: str | None, name: str = "repo") -> Path:
        repository_directory = self.root / name
        repository_directory.mkdir()
        _git(repository_directory, "init", "-q")
        if origin_url is not None:
            _git(repository_directory, "remote", "add", "origin", origin_url)
        return repository_directory


def _git(directory: Path, *all_arguments: str) -> None:
    empty_hooks = directory.parent / "no-hooks"
    empty_hooks.mkdir(exist_ok=True)
    subprocess.run(
        ["git", "-c", f"core.hooksPath={empty_hooks}", "-c", "commit.gpgsign=false", "-C", str(directory), *all_arguments],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FilingWorld:
    filing_world = FilingWorld(tmp_path)
    stand_in_gh_path = tmp_path / "stand_in_gh.py"
    stand_in_gh_path.write_text(STAND_IN_GH, encoding="utf-8")
    filing_world.lint_path.parent.mkdir(parents=True)
    filing_world.lint_path.write_text(STAND_IN_POST_LINT, encoding="utf-8")
    monkeypatch.setattr(correction_filing, "ALL_GH_COMMAND_PARTS", (sys.executable, str(stand_in_gh_path)))
    monkeypatch.setenv("STAND_IN_GH_STORE", str(filing_world.store_path))
    monkeypatch.setenv("CLAUDE_CORRECTION_CAPTURE_PATH", str(filing_world.config_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(filing_world.managed_root))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return filing_world


def _file(checkout: Path, text: str = BRIEF, *extra: str) -> int:
    return correction_filing.main(["file", "--checkout", str(checkout), "--text", text, *extra])


def test_should_file_on_the_repository_a_worktree_belongs_to(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/name", labels=("correction",))
    main_checkout = world.checkout("https://github.com/owner/name.git")
    _git(main_checkout, "commit", "-q", "--allow-empty", "-m", "start")
    worktree = world.root / "feature-worktree"
    _git(main_checkout, "worktree", "add", "-q", str(worktree))
    assert _file(worktree) == 0
    all_issues = world.issues("owner/name")
    assert len(all_issues) == 1
    assert all_issues[0]["labels"] == ["correction"]
    assert all_issues[0]["title"] == "Correction: stop opening a pull request after a correction"
    assert "Filed: https://github.com/owner/name/issues/1\n" == capsys.readouterr().out


def test_should_resolve_an_ssh_origin(world: FilingWorld) -> None:
    world.add_repository("owner/name", labels=("correction",))
    assert _file(world.checkout("git@github.com:owner/name.git")) == 0
    assert len(world.issues("owner/name")) == 1


def test_should_create_the_label_when_the_repository_lacks_it(world: FilingWorld) -> None:
    world.add_repository("owner/name")
    assert _file(world.checkout("https://github.com/owner/name")) == 0
    assert world.github()["owner/name"]["labels"] == ["correction"]
    assert world.issues("owner/name")[0]["labels"] == ["correction"]


def test_should_carry_every_brief_field_under_the_repository_preamble(world: FilingWorld) -> None:
    world.add_repository("owner/name", labels=("correction",))
    preamble_path = world.root / "preamble.md"
    preamble_path.write_text("## Request\n\n- Post corrections as issues.\n", encoding="utf-8")
    assert _file(world.checkout("https://github.com/owner/name"), BRIEF, "--preamble-file", str(preamble_path)) == 0
    body = str(world.issues("owner/name")[0]["body"])
    assert body.startswith("## Request\n\n- Post corrections as issues.\n")
    assert body.index("## Request") < body.index("## Correction")
    for each_line in BRIEF.splitlines():
        assert "> " + each_line in body
    assert "correction-lens.md" in body


def test_should_run_the_managed_post_lint_before_posting(world: FilingWorld) -> None:
    world.add_repository("owner/name", labels=("correction",))
    assert _file(world.checkout("https://github.com/owner/name")) == 0
    assert world.lint_calls() == ["issue-create owner/name"]


def _managed_root_with_the_shipped_post_lint() -> Path | None:
    for each_directory in SCRIPTS_DIRECTORY.parents:
        if (each_directory / "scripts" / "durable_post_lint.py").is_file():
            return each_directory
    return None


def test_should_post_a_body_the_shipped_post_lint_accepts(world: FilingWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    managed_root = _managed_root_with_the_shipped_post_lint()
    if managed_root is None:
        pytest.skip("the shipped durable_post_lint.py is not beside this skill")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(managed_root))
    world.add_repository("owner/name", labels=("correction",))
    assert _file(world.checkout("https://github.com/owner/name")) == 0
    assert len(world.issues("owner/name")) == 1


def test_should_file_nothing_when_the_post_lint_refuses(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/name", labels=("correction",))
    assert _file(world.checkout("https://github.com/owner/name"), BRIEF + "\nLINT-REFUSES") == 1
    assert world.issues("owner/name") == []
    error_text = capsys.readouterr().err
    assert "line 3 frames a contrast" in error_text and "Nothing was filed" in error_text


def test_should_file_nothing_without_the_managed_post_lint(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/name", labels=("correction",))
    world.lint_path.unlink()
    assert _file(world.checkout("https://github.com/owner/name")) == 1
    assert world.issues("owner/name") == []
    assert "durable_post_lint.py" in capsys.readouterr().err


def test_should_report_a_retry_of_the_same_brief_as_already_filed(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/name", labels=("correction",))
    checkout = world.checkout("https://github.com/owner/name")
    _file(checkout)
    capsys.readouterr()
    assert _file(checkout) == 0
    assert len(world.issues("owner/name")) == 1
    assert world.github()["owner/name"]["comments"] == []
    assert capsys.readouterr().out == "Already filed: https://github.com/owner/name/issues/1\n"


def test_should_mark_a_repeat_on_the_open_earlier_issue(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/name", labels=("correction",))
    checkout = world.checkout("https://github.com/owner/name")
    _file(checkout)
    capsys.readouterr()
    assert _file(checkout, BRIEF.replace("10:02", "14:40")) == 0
    assert len(world.issues("owner/name")) == 1
    all_comments = world.github()["owner/name"]["comments"]
    assert len(all_comments) == 1
    assert all_comments[0]["issue"] == 1
    assert "## Repeat" in all_comments[0]["body"] and "14:40" in all_comments[0]["body"]
    assert world.lint_calls()[-1] == "issue-comment owner/name"
    assert capsys.readouterr().out == (
        "Repeat marked on https://github.com/owner/name/issues/1: "
        "https://github.com/owner/name/issues/1#issuecomment-1\n"
    )


def test_should_file_a_repeat_of_a_closed_issue_as_a_new_issue_linking_it(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/name", labels=("correction",))
    checkout = world.checkout("https://github.com/owner/name")
    _file(checkout)
    world.close_issue("owner/name", 1)
    capsys.readouterr()
    assert _file(checkout, BRIEF.replace("10:02", "14:40")) == 0
    all_issues = world.issues("owner/name")
    assert len(all_issues) == 2
    assert "Repeat of https://github.com/owner/name/issues/1" in str(all_issues[1]["body"])
    assert capsys.readouterr().out == (
        "Filed: https://github.com/owner/name/issues/2, a repeat of https://github.com/owner/name/issues/1\n"
    )


def test_should_replay_a_supplied_key_once_and_mark_a_new_message_as_a_repeat(world: FilingWorld) -> None:
    world.add_repository("owner/name", labels=("correction",))
    checkout = world.checkout("https://github.com/owner/name")
    _file(checkout, "first", "--source", "flag", "--dedupe-key", "msg-7")
    _file(checkout, "first", "--source", "flag", "--dedupe-key", "msg-7")
    _file(checkout, "second", "--source", "flag", "--dedupe-key", "msg-8")
    assert len(world.issues("owner/name")) == 2
    assert world.github()["owner/name"]["comments"] == []
    assert "Source: flag" in str(world.issues("owner/name")[0]["body"])


def test_should_dedupe_from_the_ledger_when_the_listing_lags(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/name", labels=("correction",))
    checkout = world.checkout("https://github.com/owner/name")
    _file(checkout)
    store = world.github()
    store["owner/name"]["issues"] = []
    world.store_path.write_text(json.dumps(store), encoding="utf-8")
    capsys.readouterr()
    _file(checkout)
    assert capsys.readouterr().out == "Already filed: https://github.com/owner/name/issues/1\n"


def test_should_mask_secrets_and_emails_in_every_repository(world: FilingWorld) -> None:
    world.add_repository("owner/name", labels=("correction",))
    _file(world.checkout("https://github.com/owner/name"), "you leaked ghp_" + "a" * 36 + " and me@example.com")
    body = str(world.issues("owner/name")[0]["body"])
    assert "ghp_" not in body and "me@example.com" not in body
    assert body.count("[redacted]") == 2


def test_should_keep_paths_in_a_private_repository(world: FilingWorld) -> None:
    world.add_repository("owner/name", private=True, labels=("correction",))
    _file(world.checkout("https://github.com/owner/name"), "Where: C:\\Users\\someone\\code\\tool.py")
    assert "C:\\Users\\someone\\code\\tool.py" in str(world.issues("owner/name")[0]["body"])


def test_should_mask_paths_account_names_and_other_repositories_in_a_public_repository(world: FilingWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERNAME", "pat-local")
    world.add_repository("owner/name", private=False, labels=("correction",))
    text = (
        "Correction: pat-local saw C:\\Users\\pat-local\\code\\tool.py and /home/pat/notes.md\n"
        "Where: https://github.com/someorg/private-tool/pull/3 and https://github.com/owner/name/pull/9"
    )
    assert _file(world.checkout("https://github.com/owner/name"), text) == 0
    issue = world.issues("owner/name")[0]
    body = str(issue["body"])
    for each_private in ("pat-local", "C:\\Users", "/home/pat", "someorg", "private-tool"):
        assert each_private not in body and each_private not in str(issue["title"])
    assert "https://github.com/owner/name/pull/9" in body


def test_should_fall_back_to_the_inbox_and_say_why_when_the_repository_is_unreachable(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/inbox", labels=("correction",))
    world.set_inbox("owner/inbox")
    assert _file(world.checkout("https://github.com/owner/gone")) == 0
    assert len(world.issues("owner/inbox")) == 1
    printed_line = capsys.readouterr().out
    assert printed_line.startswith("Filed: https://github.com/owner/inbox/issues/1 (fallback: ")
    assert "owner/gone" in printed_line and "HTTP 404" in printed_line


def test_should_fall_back_when_the_repository_has_issues_turned_off(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/name", has_issues=False)
    world.add_repository("owner/inbox", labels=("correction",))
    world.set_inbox("owner/inbox")
    assert _file(world.checkout("https://github.com/owner/name")) == 0
    assert world.issues("owner/name") == []
    assert "owner/name has issues turned off" in capsys.readouterr().out


def test_should_fall_back_when_the_session_has_no_repository(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/inbox", labels=("correction",))
    world.set_inbox("owner/inbox")
    plain_folder = world.root / "notes"
    plain_folder.mkdir()
    assert _file(plain_folder) == 0
    assert len(world.issues("owner/inbox")) == 1
    assert "no origin remote" in capsys.readouterr().out


def test_should_fall_back_when_origin_is_not_on_github(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/inbox", labels=("correction",))
    world.set_inbox("owner/inbox")
    assert _file(world.checkout("https://gitlab.example/owner/name.git")) == 0
    assert "is not a GitHub repository" in capsys.readouterr().out


def test_should_file_nothing_and_say_why_without_a_reachable_repository_or_inbox(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    assert _file(world.checkout("https://github.com/owner/gone")) == 1
    error_text = capsys.readouterr().err
    assert "owner/gone" in error_text and "Nothing was filed" in error_text
    assert "Print the brief in your reply" in error_text


def test_should_file_nothing_for_empty_text(world: FilingWorld) -> None:
    world.add_repository("owner/name", labels=("correction",))
    assert _file(world.checkout("https://github.com/owner/name"), "   ") == 1
    assert world.issues("owner/name") == []


def test_should_list_the_open_corrections_of_the_checkout_repository(world: FilingWorld, capsys: pytest.CaptureFixture[str]) -> None:
    world.add_repository("owner/name", labels=("correction",))
    checkout = world.checkout("https://github.com/owner/name")
    correction_filing.main(["list", "--checkout", str(checkout)])
    assert capsys.readouterr().out == "No open corrections.\n"
    _file(checkout)
    capsys.readouterr()
    correction_filing.main(["list", "--checkout", str(checkout)])
    assert capsys.readouterr().out == (
        "#1 Correction: stop opening a pull request after a correction "
        "https://github.com/owner/name/issues/1\n"
    )


def test_should_default_the_checkout_to_the_working_directory(world: FilingWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    world.add_repository("owner/name", labels=("correction",))
    monkeypatch.chdir(world.checkout("https://github.com/owner/name"))
    assert correction_filing.main(["file", "--text", BRIEF]) == 0
    assert len(world.issues("owner/name")) == 1


def test_should_read_the_text_from_stdin_without_expanding_it(world: FilingWorld, monkeypatch: pytest.MonkeyPatch) -> None:
    world.add_repository("owner/name", labels=("correction",))
    checkout = world.checkout("https://github.com/owner/name")
    piped_bytes = 'say "$(whoami)" and `id` in caf\u00e9\n'.encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(piped_bytes), encoding="cp1252"))
    assert correction_filing.main(["file", "--checkout", str(checkout)]) == 0
    assert '> say "$(whoami)" and `id` in caf\u00e9' in str(world.issues("owner/name")[0]["body"])


def test_should_title_a_raw_correction_from_its_text() -> None:
    assert correction_filing.issue_title_for("a\nb") == "Correction: a b"
    assert correction_filing.issue_title_for(BRIEF) == "Correction: stop opening a pull request after a correction"


@pytest.mark.parametrize(
    ("origin_url", "repository"),
    [
        ("https://github.com/owner/name.git", "owner/name"),
        ("https://github.com/owner/name", "owner/name"),
        ("git@github.com:owner/name.git", "owner/name"),
        ("ssh://git@github.com/owner/name.git", "owner/name"),
        ("https://user@github.com/owner/name.git", "owner/name"),
    ],
)
def test_should_read_owner_and_name_from_a_github_origin(origin_url: str, repository: str) -> None:
    assert correction_filing.github_repository_from_origin(origin_url) == repository


def test_should_read_no_repository_from_another_host() -> None:
    assert correction_filing.github_repository_from_origin("https://gitlab.example/owner/name.git") == ""
