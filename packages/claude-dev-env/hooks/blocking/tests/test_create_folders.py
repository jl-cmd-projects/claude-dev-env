"""Behavioral tests for giving each shell create the folder it runs in.

(cd sub && gh pr create) ; gh pr create   -> sub, then the starting folder
pushd sub && popd && gh pr create         -> the starting folder
cd "$WORK" && gh pr create                -> folder not followed
gh pr create --body-file - <<'EOF' ...    -> one create; the body names none
"""

from __future__ import annotations

import pytest

from blocking.merge_review_gate_parts import create_folders
from blocking.merge_review_gate_parts.create_folders import PlacedCreate, all_placed_creates

START = "/work/main"


def _placements(command: str) -> list[tuple[tuple[str, ...], str | None, bool]]:
    return list(
        dict.fromkeys(
            (
                tuple(each_argument.strip("\"'") for each_argument in each_create.all_arguments),
                each_create.folder,
                each_create.is_folder_followed,
            )
            for each_create in all_placed_creates(command, START)
        )
    )


def test_should_keep_a_subshell_folder_change_inside_the_subshell() -> None:
    assert _placements("(cd ../rsub && gh pr create --fill) ; gh pr create --fill") == [
        (("--fill",), "/work/main/../rsub", True),
        (("--fill",), START, True),
    ]


@pytest.mark.parametrize(
    "command",
    [
        "cd sub ; (cd ../rco && (true)) ; gh pr create --fill",
        "cd sub ; (cd ../rco && (true)\n) ; gh pr create --fill",
        "cd sub ; (cd ../rco && ( true ) ) ; gh pr create --fill",
        "cd sub ; ((cd ../rco)) ; gh pr create --fill",
        "cd sub ; (true && (cd ../rco)) ; gh pr create --fill",
        "cd sub && (cd ../rco && (cd x)) && gh pr create --fill",
    ],
)
def test_should_return_to_the_folder_before_the_outer_subshell_when_nested_subshells_close(command: str) -> None:
    assert _placements(command) == [(("--fill",), "/work/main/sub", True)]


def test_should_return_to_the_inner_subshell_start_when_only_the_inner_one_closes() -> None:
    assert _placements("cd sub ; (cd ../rco ; (cd x) ; gh pr create --fill) ; gh pr create --fill") == [
        (("--fill",), "/work/main/sub/../rco", True),
        (("--fill",), "/work/main/sub", True),
    ]


def test_should_return_to_the_pushed_folder_at_popd() -> None:
    assert _placements("pushd ../rsub && gh pr create --fill && popd && gh pr create --fill") == [
        (("--fill",), "/work/main/../rsub", True),
        (("--fill",), START, True),
    ]


def test_should_carry_a_plain_cd_to_every_later_create() -> None:
    assert _placements("cd sub && gh pr create --head a; gh pr new --head b") == [
        (("--head", "a"), "/work/main/sub", True),
        (("--head", "b"), "/work/main/sub", True),
    ]


@pytest.mark.parametrize("folder_word", ['"$WORK"', "$(pwd)/x", "-", "../*"])
def test_should_leave_a_folder_it_cannot_follow_unfollowed(folder_word: str) -> None:
    all_placements = _placements(f"cd {folder_word} && gh pr create --fill")
    assert all_placements and all(not each_placement[2] for each_placement in all_placements)


def test_should_leave_popd_with_nothing_pushed_unfollowed() -> None:
    assert _placements("popd; gh pr create --fill") == [(("--fill",), None, False)]


def test_should_keep_a_background_cd_out_of_later_creates() -> None:
    assert _placements("cd other & gh pr create --fill") == [(("--fill",), START, True)]


@pytest.mark.parametrize(
    "command",
    [
        "cd sub | true; gh pr create --fill",
        "true | cd sub; gh pr create --fill",
        "{ cd ../rsub; } | true; gh pr create --fill",
        "{ cd sub; }; gh pr create --fill",
        "if true; then cd sub; fi; gh pr create --fill",
        "if true; then true; cd sub; fi; gh pr create --fill",
        "! if true; then cd sub; fi; gh pr create --fill",
        "case a in a) cd sub;; esac; gh pr create --fill",
        "for each in sub; do cd $each; done; gh pr create --fill",
        "while false; do cd sub; done; gh pr create --fill",
        "f() { cd sub; }; gh pr create --fill",
        ">/dev/null cd sub; gh pr create --fill",
    ],
)
def test_should_leave_a_create_after_an_unmodeled_folder_change_unfollowed(command: str) -> None:
    all_placements = _placements(command)
    assert all_placements and all(not each_placement[2] for each_placement in all_placements)


@pytest.mark.parametrize("prefix", ["builtin", "command"])
def test_should_follow_cd_after_a_builtin_or_command_prefix(prefix: str) -> None:
    assert _placements(f"{prefix} cd sub && gh pr create --fill") == [
        (("--fill",), "/work/main/sub", True)
    ]


def test_should_read_a_create_a_bash_wrapper_runs_in_the_folder_before_it() -> None:
    assert _placements(
        'cd sub && bash -c "cd inner && gh pr create --head two"; gh pr create --head three'
    ) == [
        (("--head", "two"), "/work/main/sub/inner", True),
        (("--head", "three"), "/work/main/sub", True),
    ]


def test_should_let_eval_change_the_folder_of_its_own_shell() -> None:
    assert _placements("eval 'cd sub'; gh pr create --fill") == [
        (("--fill",), "/work/main/sub", True)
    ]


def test_should_follow_a_powershell_path_parameter() -> None:
    assert _placements("Set-Location -Path sub; gh pr create --fill") == [
        (("--fill",), "/work/main/sub", True)
    ]


def test_should_go_home_for_a_bare_cd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    assert _placements("cd && gh pr create --fill") == [(("--fill",), "/home/tester", True)]


def test_should_read_no_create_in_a_heredoc_body() -> None:
    command = "gh pr create --head two --body-file - <<'EOF'\ngh pr create --head one\nEOF"
    assert {each_placement[0][:2] for each_placement in _placements(command)} == {("--head", "two")}


def test_should_read_no_create_in_a_quoted_option_value() -> None:
    command = 'gh pr create --head two --label "see gh pr create" --repo acme/tools'
    assert {each_placement[0] for each_placement in _placements(command)} == {
        ("--head", "two", "--label", "see gh pr create", "--repo", "acme/tools")
    }


def test_should_read_a_create_inside_a_substitution() -> None:
    assert ("--head", "two") in {
        each_placement[0] for each_placement in _placements('echo "$(gh pr create --head two)"')
    }


def test_should_place_a_create_after_a_line_break_inside_a_substitution() -> None:
    assert _placements("x=$(true\ngh pr create --head two)") == [(("--head", "two"), START, True)]


@pytest.mark.parametrize(
    "command",
    [
        'gh pr create --head one && bash -c "true\ngh pr create --head two"',
        "gh pr create --head one && eval 'true\ngh pr create --head two'",
        "cd sub && gh pr create --head one --body $'it\\'s' ; gh pr create --head two",
        "gh pr create --head one --body \"$(echo '\"')\" ; gh pr create --head two",
    ],
)
def test_should_place_each_create_bash_runs(command: str) -> None:
    assert ("--head", "two") in {each_placement[0][-2:] for each_placement in _placements(command)}


@pytest.mark.parametrize(
    "command",
    [
        "cd sub && eval 'gh pr create --head two --body \"a b\"'",
        "cd sub && eval \"gh pr create --head two --body 'a b'\"",
    ],
)
def test_should_read_a_create_eval_runs_with_a_quoted_value(command: str) -> None:
    assert _placements(command) == [(("--head", "two", "--body", "a b"), "/work/main/sub", True)]


def test_should_read_a_create_a_wrapper_runs_in_a_case_arm() -> None:
    command = (
        "case x in x) eval 'gh pr create --head two';; "
        "(y) bash -c 'gh pr create --head three';; esac"
    )
    assert {each_placement[0] for each_placement in _placements(command)} == {
        ("--head", "two"),
        ("--head", "three"),
    }


def test_should_read_a_create_in_a_subshell_a_redirect_follows() -> None:
    assert [
        (each_placement[0][:2], each_placement[1], each_placement[2])
        for each_placement in _placements("cd sub && (gh pr create --head two) > log")
    ] == [(("--head", "two"), "/work/main/sub", True)]


@pytest.mark.parametrize(
    ("command", "all_arguments"),
    [
        ("bash -c \"gh pr create --head one --body 'a\nb'\"", ("--head", "one", "--body", "a\nb")),
        (
            "gh pr create --head one --body 'a\ngh pr create --head two\nb'",
            ("--head", "one", "--body", "a\ngh pr create --head two\nb"),
        ),
    ],
)
def test_should_place_only_the_create_bash_runs_when_a_quoted_value_spans_lines(
    command: str, all_arguments: tuple[str, ...]
) -> None:
    assert _placements(command) == [(all_arguments, START, True)]


def test_should_read_an_ansi_c_quoted_value_as_one_word() -> None:
    assert _placements("gh pr create --head one --body $'it\\'s\\n; x'") == [
        (("--head", "one", "--body", "it's\n; x"), START, True)
    ]


def test_should_leave_a_create_only_the_wrapped_reading_finds_unfollowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(create_folders, "_walk_text", lambda _walk, _text, state, _depth: state)
    assert all_placed_creates('bash -c "cd sub && gh pr create --fill"', START) == [
        PlacedCreate(("--fill",), None, False)
    ]


def test_should_read_an_unbalanced_command_both_ways() -> None:
    assert ("--head", "two") in {
        each_placement[0][-2:]
        for each_placement in _placements('gh pr create --head one --body "a\\" ; gh pr create --head two')
    }


def test_should_read_no_create_in_a_heredoc_inside_a_substitution_body() -> None:
    command = "gh pr create --head one --body \"$(cat <<'B'\nsee gh pr create --head two \"q\"\nB\n)\""
    assert {each_placement[0][:2] for each_placement in _placements(command)} == {("--head", "one")}


@pytest.mark.parametrize(
    ("command", "body"),
    [
        (
            'gh pr create --head one --body "say \\"x\\" ; gh pr create --head two"',
            'say "x" ; gh pr create --head two',
        ),
        (
            "gh pr create --head one --body 'say \\\"x\\\" ; gh pr create --head two'",
            'say \\"x\\" ; gh pr create --head two',
        ),
    ],
)
def test_should_read_a_quoted_value_with_an_escaped_quote_as_one_word(
    command: str, body: str
) -> None:
    assert _placements(command) == [(("--head", "one", "--body", body), START, True)]


def test_should_return_placed_creates() -> None:
    assert all_placed_creates("gh pr create --fill", START) == [
        PlacedCreate(("--fill",), START, True)
    ]


@pytest.mark.parametrize(
    "command",
    [
        "eval " * 18 + "'gh pr create --head two'",
        "bash -c '" + "eval " * 18 + "gh pr create --head two'",
        "eval " * 18 + "'python3 pull_request.py create'",
    ],
)
def test_should_leave_unread_a_create_past_the_unwrap_depth(command: str) -> None:
    assert _placements(command) == [((), None, False)]


def test_should_read_no_create_in_text_past_the_unwrap_depth_that_holds_none() -> None:
    assert _placements("eval " * 18 + "'echo hi'") == []

