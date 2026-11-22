"""Behavior tests for settled_steps, the shapes a create counts as settled."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

hooks_directory = str(Path(__file__).resolve().parent.parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.merge_review_gate_parts.settled_steps import (
    holds_expanding_heredoc,
    holds_process_substitution,
    holds_subscript_expansion,
    holds_unsettled_expansion,
    is_settled_create_segment,
    is_settled_pipe_reader,
    is_settled_step,
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
        (["uv", "run", "pull_request.py", "create"], True),
        (["python3", "/x/pull_request.py", "create"], True),
        (["/srv/u/.agents/skills/pull-request/scripts/pull_request.py", "create"], True),
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
