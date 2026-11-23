"""Behavior tests for settled_steps, the shapes a create counts as settled."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.merge_review_gate_parts.create_folders import all_placed_creates
from blocking.merge_review_gate_parts.settled_steps import (
    holds_expanding_heredoc,
    holds_process_substitution,
    holds_subscript_expansion,
    holds_unsettled_expansion,
    is_managed_launcher,
    is_settled_create_segment,
    is_settled_pipe_reader,
    is_settled_step,
    with_launcher_home_written,
    with_managed_launcher_home,
)

CREATE_WORDS = ["gh", "pr", "create"]


@pytest.mark.parametrize(
    ("text", "is_held"),
    [("cat <(x) && y", True), ("y --fill 2> >(x)", True), ("y --fill 2>&1", False)],
)
def test_should_find_a_process_substitution_anywhere(text: str, is_held: bool) -> None:
    assert holds_process_substitution(text) is is_held


@pytest.mark.parametrize(
    ("text", "is_held"),
    [
        ("echo ${b[X]}; y", True),
        ('y --title "${!b[@]}"', True),
        ("echo ${#b[0]} && y", True),
        ("echo ${b} $b[X] && y", False),
    ],
)
def test_should_find_an_array_subscript_expansion_anywhere(text: str, is_held: bool) -> None:
    assert holds_subscript_expansion(text) is is_held


@pytest.mark.parametrize(
    ("text", "is_held"),
    [
        ('y --title "$[PATH=0]" --fill', True),
        ('y --title "x$[PATH=0]" --fill', True),
        ('y --title "$[HOME=1]" --fill', True),
        ("echo $[PATH=0]; y", True),
        ('y --title "$((PATH=0))"', True),
        ("echo $((HOME=0)) && y", True),
        ('y --title "${T:PATH=0}"', True),
        ('y --title "${T: -1}"', True),
        ('y --title "${@:1:HOME=5}"', True),
        ('y --title "$(echo \')"\' $[PATH=0])"', True),
        ("y --title \"it's $[PATH=0]\"", True),
        ("cat <<'EOF'\nit's\nEOF\ny --title \"$[PATH=0]\"", True),
        ("y --title 'a\n$[PATH=0]", True),
        ("y --title '$[PATH=0]' --fill", False),
        ("y --title '$((PATH=0))' --fill", False),
        ("y --title \\$[PATH=0]", False),
        ('y --title "${BASH_COMMAND@P}" --fill', True),
        ('y --title "${T@E}"', True),
        ('y --title "${T@A}"', True),
        ('y --title "${GH_REPO:=x}"', True),
        ('y --title "${GH_REPO=x}"', True),
        ('y --title "${!T}"', True),
        ('y --title "${T/a/b}"', True),
        ('y --title "${#T}"', True),
        ('y --title "${T^^}"', True),
        ('y --title "${T#a}" --body "${T%b}"', True),
        ('y --title "${T:-${X@P}}"', True),
        ("echo ${T@P}; y", True),
        ("y --title 'a\n${T@P}", True),
        ("y --title '${BASH_COMMAND@P}' --fill", False),
        ("y --title \\${T@P}", False),
        ('y --title "${T}" --body "${T_2}${1}"', False),
        ('y --title "${T:-x}" --body "${B-y}${C:+z}${D:?e}"', False),
        ('y --title "$(cat f)" --label "$L"', False),
        ("cat <<'EOF'\n$[PATH=0]\nEOF\ny --fill", False),
    ],
)
def test_should_find_an_unsettled_expansion_outside_single_quotes(text: str, is_held: bool) -> None:
    assert holds_unsettled_expansion(text) is is_held


@pytest.mark.parametrize(
    ("text", "is_expanding"),
    [
        ("cat <<EOF\n$(x)\nEOF\n", True),
        ("cat <<-EOF\n\t`x`\n\tEOF\n", True),
        ("cat <<'EOF'\n$(x)\nEOF\n", False),
        ("cat <<\\EOF\n$(x)\nEOF\n", False),
        ("cat <<EOF\nplain\nEOF\necho $X\n", False),
    ],
)
def test_should_find_a_heredoc_body_bash_expands(text: str, is_expanding: bool) -> None:
    assert holds_expanding_heredoc(text) is is_expanding


@pytest.mark.parametrize(
    ("all_tokens", "is_in_create_words", "is_settled"),
    [
        (["cd", "../a"], False, True),
        (["echo", "hi", "2", ">&", "1", ">", "/dev/null"], False, True),
        (["head", "-n1", "f"], False, True),
        (["head", "-n1", "f"], True, False),
        (["cat", "body.md"], True, True),
        (["cd", "docs"], False, True),
        (["cd", "sub/"], False, True),
        (["cd", ".github"], False, True),
        (["pushd", "../a"], False, True),
        (["cd", ".git"], False, False),
        (["cd", ".git/"], False, False),
        (["cd", "./.git"], False, False),
        (["cd", ".GIT"], False, False),
        (["cd", ".git."], False, False),
        (["cd", ".git/refs/heads"], False, False),
        (["cd", "../.git"], False, False),
        (["cd", "sub\\.Git\\refs"], False, False),
        (["cd", "../tools.git"], False, False),
        (["pushd", ".git"], False, False),
        (["cd", "-P", ".git"], False, False),
        (["cd", "-P", "sub"], False, False),
        (["cd", "-"], False, False),
        (["cd"], False, False),
        (["cd", ".gi?"], False, False),
        (["cd", "~/checkout"], False, True),
        (["cd", "~"], False, True),
        (["cd", ".", "2", ">", "/dev/null"], False, True),
        (["cd", "~/.git"], False, False),
        (["cd", "~-"], False, False),
        (["cd", "~other/x"], False, False),
        (["cd", "sub", "2", ">", "/dev/null", ".git"], False, False),
        (["cd", ".", ">", "f"], False, False),
        (["pushd", "+1"], False, False),
        (["pushd"], False, False),
        (["popd"], False, False),
        (["cd", "$X"], False, False),
        (["./cat"], False, False),
        (["X=1"], False, False),
        (["echo", "a", ">", "f"], False, False),
        (["printf", "-v", "GH_REPO", "x"], False, False),
        (["printf", "$", "X", "%s", "y"], False, False),
        (["printf", "${Z:--v}", "X", "%s", "y"], False, False),
        (["printf", "%s", "$T"], True, True),
        (["echo", "$"], False, False),
        (["cd", "$"], False, False),
        (["cat", "--", "$F"], False, True),
        (["tee", "out.txt"], False, False),
        (["export", "A=b"], False, False),
        (["p", "()"], False, False),
        ([], False, True),
    ],
)
def test_should_count_only_the_listed_steps_as_settled(
    all_tokens: list[str], is_in_create_words: bool, is_settled: bool
) -> None:
    assert is_settled_step(all_tokens, is_in_create_words, False) is is_settled


def test_should_not_settle_a_heredoc_step_when_a_body_expands() -> None:
    assert is_settled_step(["cat", "<<", "EOF"], False, False) is True
    assert is_settled_step(["cat", "<<", "EOF"], False, True) is False


@pytest.mark.parametrize(
    ("all_tokens", "is_settled"),
    [
        ([*CREATE_WORDS, "--fill"], True),
        (["X=1", *CREATE_WORDS, "--fill", ">", "pr.txt"], True),
        (["GH_REPO=a/b", *CREATE_WORDS], True),
        (["gh_repo=acme/other", *CREATE_WORDS], False),
        (["Path=/x", *CREATE_WORDS], False),
        ([*CREATE_WORDS, ">", ".gi?/HEAD"], False),
        ([*CREATE_WORDS, ">", "{a,.git}/HEAD"], False),
        ([*CREATE_WORDS, ">", "pr{1,2}.txt"], False),
        (["uv", "run", "pull_request.py", "create"], False),
        (["python3", "/x/pull_request.py", "create"], False),
        (["./gh", "pr", "create"], False),
        (["/tmp/x/gh", "pr", "create"], False),
        (["bin\\gh.exe", "pr", "create"], False),
        (["./python3", "/x/pull_request.py", "create"], False),
        (["uv", "run", "/tmp/x/python3", "pull_request.py", "create"], False),
        (["X=$(git push)", *CREATE_WORDS], False),
        (["GIT_DIR=x", *CREATE_WORDS], False),
        (["LD_PRELOAD=x.so", *CREATE_WORDS], False),
        (["env", *CREATE_WORDS], False),
        (["command", *CREATE_WORDS], False),
        ([*CREATE_WORDS, ">", ".git/HEAD"], False),
        ([*CREATE_WORDS, ">", "$F"], False),
        (["git", "commit"], False),
    ],
)
def test_should_settle_a_create_segment_only_with_plain_prefixes_and_kept_output(
    all_tokens: list[str], is_settled: bool
) -> None:
    assert is_settled_create_segment(all_tokens, False) is is_settled


MANAGED_LAUNCHER_TAIL = ".agents/skills/pull-request/scripts/pull_request.py"


@pytest.fixture
def managed_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return f"{home.as_posix()}/{MANAGED_LAUNCHER_TAIL}"


@pytest.mark.parametrize(
    "command_template",
    [
        "{launcher} create --head f",
        "python3 {launcher} create --head f",
        "python {launcher} create --head f",
    ],
)
def test_should_settle_a_launcher_create_whose_script_is_the_managed_launcher(
    managed_launcher: str, command_template: str
) -> None:
    all_tokens = command_template.format(launcher=managed_launcher).split()
    assert is_settled_create_segment(all_tokens, False) is True


@pytest.mark.parametrize(
    "command_template",
    [
        "pull_request.py create --head f",
        "./pull_request.py create --head f",
        "/tmp/x/pull_request.py create --head f",
        "scripts/pull_request.py create --head f",
        "python3 pull_request.py create --head f",
        "python3 ./pull_request.py create --head f",
        "python3 /tmp/x/pull_request.py create --head f",
        "uv run pull_request.py create --head f",
        "uv run ./pull_request.py create --head f",
        "uv run /tmp/x/pull_request.py create --head f",
        "uv run python3 ./pull_request.py create --head f",
        f"python3 /opt/lookalike/{MANAGED_LAUNCHER_TAIL} create --head f",
        "python3 ~/pull-request/scripts/pull_request.py create --head f",
        f"python3 ~other/{MANAGED_LAUNCHER_TAIL} create --head f",
        "./python3 {launcher} create --head f",
        "python3.11 {launcher} create --head f",
        "python3 -u {launcher} create --head f",
        "py -3 {launcher} create --head f",
        f"python3 ~/{MANAGED_LAUNCHER_TAIL} create --head f",
        f"$HOME/{MANAGED_LAUNCHER_TAIL} create --head f",
        "python3 '{launcher}' create --head f",
        "PYTHONPATH=/x python3 {launcher} create --head f",
        "PYTHONHOME=/x python3 {launcher} create --head f",
        "PYTHONSTARTUP=/x/s.py python3 {launcher} create --head f",
        "PYTHONUSERBASE=/x python3 {launcher} create --head f",
        "UV_PYTHON=/x/python3 uv run {launcher} create --head f",
        "uv run {launcher} create --head f",
        "uv run python3 {launcher} create --head f",
        "uv run python {launcher} create --head f",
        "uv run --no-project python3 {launcher} create --head f",
        "X=1 python3 {launcher} create --head f",
        "X=1 {launcher} create --head f",
        "VIRTUAL_ENV=/x python3 {launcher} create --head f",
        "CONDA_PREFIX=/x python3 {launcher} create --head f",
        "CONDA_DEFAULT_ENV=x {launcher} create --head f",
        "GH_REPO=acme/tools python3 {launcher} create --head f",
        "BASH_ENV=/x/rc {launcher} create --head f",
        "env python3 {launcher} create --head f",
        "env {launcher} create --head f",
        "exec python3 {launcher} create --head f",
        "exec {launcher} create --head f",
        "command python3 {launcher} create --head f",
        "nice python3 {launcher} create --head f",
        "nice {launcher} create --head f",
        "time python3 {launcher} create --head f",
        "sudo python3 {launcher} create --head f",
        "conda run python3 {launcher} create --head f",
    ],
)
def test_should_not_settle_a_launcher_create_whose_script_is_not_the_managed_launcher(
    managed_launcher: str, command_template: str
) -> None:
    all_tokens = command_template.format(launcher=managed_launcher).split()
    assert is_settled_create_segment(all_tokens, False) is False


def test_should_name_the_managed_launcher_only_by_its_absolute_path_under_home(managed_launcher: str) -> None:
    folder_of_launcher, _, file_name = managed_launcher.rpartition("/")
    assert is_managed_launcher(managed_launcher) is True
    assert is_managed_launcher(f"{folder_of_launcher}/../scripts/{file_name}") is True
    assert is_managed_launcher(MANAGED_LAUNCHER_TAIL) is False
    assert is_managed_launcher(f"/opt/lookalike/{MANAGED_LAUNCHER_TAIL}") is False


def test_should_write_out_only_the_home_prefix_of_the_managed_launcher(managed_launcher: str) -> None:
    home = managed_launcher.removesuffix(f"/{MANAGED_LAUNCHER_TAIL}")
    assert with_managed_launcher_home(f"python3 ~/{MANAGED_LAUNCHER_TAIL} create") == (
        f"python3 {home}/{MANAGED_LAUNCHER_TAIL} create"
    )
    assert with_managed_launcher_home(f"$HOME/{MANAGED_LAUNCHER_TAIL} create") == f"{home}/{MANAGED_LAUNCHER_TAIL} create"
    assert with_managed_launcher_home("python3 ~/x/pull_request.py create") == "python3 ~/x/pull_request.py create"


@pytest.mark.parametrize(
    ("command", "is_settled"),
    [
        (f"python3 ~/{MANAGED_LAUNCHER_TAIL} create --head f", True),
        (f"~/{MANAGED_LAUNCHER_TAIL} create --head f", True),
        (f"$HOME/{MANAGED_LAUNCHER_TAIL} create --head f", True),
        (f'python3 "$HOME/{MANAGED_LAUNCHER_TAIL}" create --head f', True),
        (f'python3 "$HOME"/{MANAGED_LAUNCHER_TAIL} create --head f', True),
        (f"cd . && python3 ~/{MANAGED_LAUNCHER_TAIL} create --head f", True),
        (f"python3 '~/{MANAGED_LAUNCHER_TAIL}' create --head f", False),
        (f'python3 "~/{MANAGED_LAUNCHER_TAIL}" create --head f', False),
        (f"python3 \\~/{MANAGED_LAUNCHER_TAIL} create --head f", False),
        (f"python3 ''~/{MANAGED_LAUNCHER_TAIL} create --head f", False),
        (f'python3 ~"/{MANAGED_LAUNCHER_TAIL}" create --head f', False),
        (f"python3 '$HOME/{MANAGED_LAUNCHER_TAIL}' create --head f", False),
        (f"python3 \\$HOME/{MANAGED_LAUNCHER_TAIL} create --head f", False),
        (f'python3 $"HOME"/{MANAGED_LAUNCHER_TAIL} create --head f', False),
        (f"echo ~/{MANAGED_LAUNCHER_TAIL}; python3 '~/{MANAGED_LAUNCHER_TAIL}' create --head f", False),
        (f"PYTHONPATH=/x python3 ~/{MANAGED_LAUNCHER_TAIL} create --head f", False),
    ],
)
def test_should_settle_a_launcher_create_only_when_bash_writes_out_its_home(
    managed_launcher: str, tmp_path: Path, command: str, is_settled: bool
) -> None:
    all_creates = all_placed_creates(command, tmp_path.as_posix())
    assert [each_create.is_head_settled for each_create in all_creates] == [is_settled]


def test_should_write_out_only_a_launcher_home_that_bash_expands(managed_launcher: str) -> None:
    unquoted_line = f"python3 ~/{MANAGED_LAUNCHER_TAIL} create"
    quoted_line = f"python3 '~/{MANAGED_LAUNCHER_TAIL}' create"
    quoted_tokens = ["python3", f"~/{MANAGED_LAUNCHER_TAIL}", "create"]
    assert with_launcher_home_written(unquoted_line, quoted_tokens) == ["python3", managed_launcher, "create"]
    assert with_launcher_home_written(quoted_line, quoted_tokens) == quoted_tokens


@pytest.mark.parametrize(
    ("all_tokens", "is_settled"),
    [
        (["tail", "-5"], True),
        (["tee", "out.txt"], True),
        (["grep", "-v", "x"], True),
        (["grep", "-o", "https.*"], True),
        (["tee", ".git/HEAD"], False),
        (["tee", ".gi?/HEAD"], False),
        (["tee", ".g*/HEAD"], False),
        (["tee", ".gi[t]/HEAD"], False),
        (["tee", "~/x"], False),
        (["cat", ">", ".gi?/HEAD"], False),
        (["cat", ">", ".git/HEAD"], False),
        (["cat", "$F"], False),
        (["git", "push"], False),
        ([], False),
    ],
)
def test_should_settle_only_a_reader_after_a_create_in_a_pipeline(
    all_tokens: list[str], is_settled: bool
) -> None:
    assert is_settled_pipe_reader(all_tokens, False) is is_settled
