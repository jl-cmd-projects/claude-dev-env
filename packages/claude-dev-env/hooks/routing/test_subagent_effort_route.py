import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hooks_constants.subagent_effort_route_constants import ALL_BUILT_IN_EFFORT_LEVELS_BY_FAMILY
from subagent_effort_route import (
    FamilyEfforts,
    load_effort_levels,
    model_family,
    parsed_effort_levels,
    route_spawn_input,
    routed_effort,
)

EFFORT_LEVELS_TABLE = {
    "opus": {"allowed": ["medium", "high"], "default": "medium"},
    "sonnet": {"allowed": ["high"], "default": "high"},
    "fable": {"allowed": ["low", "medium", "high"], "default": "high"},
    "haiku": {"allowed": ["low", "medium", "high", "xhigh", "max"], "default": "medium"},
}
SHIPPED_EFFORT_LEVELS_PATH = (
    Path(__file__).resolve().parent.parent / "hooks_constants" / "subagent_effort_levels.json"
)
ROUTING_DIRECTORY = Path(__file__).resolve().parent
FIFO_RUN_TIMEOUT_SECONDS = 5
LOAD_LEVELS_SCRIPT = (
    "import sys; from pathlib import Path; from subagent_effort_route import load_effort_levels; "
    "print(sorted(load_effort_levels(Path(sys.argv[1]))))"
)


def _write_levels(tmp_path: Path, levels_text: str) -> Path:
    levels_path = tmp_path / "subagent_effort_levels.json"
    levels_path.write_text(levels_text, encoding="utf-8")
    return levels_path


@pytest.fixture
def effort_levels(tmp_path: Path) -> dict[str, FamilyEfforts]:
    return load_effort_levels(_write_levels(tmp_path, json.dumps(EFFORT_LEVELS_TABLE)))


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("opus", "opus"),
        ("claude-opus-5-5", "opus"),
        ("Sonnet", "sonnet"),
        ("claude-fable-5-2", "fable"),
        ("claude-haiku-5-5", "haiku"),
        ("inherit", None),
        ("gpt-5", None),
        (None, None),
        (7, None),
    ],
)
def test_should_name_the_family_of_a_model(
    effort_levels: dict[str, FamilyEfforts], model: object, family: str | None
) -> None:
    assert model_family(model, effort_levels) == family


@pytest.mark.parametrize(
    ("family", "effort", "expected"),
    [
        ("opus", "high", "high"),
        ("opus", "medium", "medium"),
        ("opus", "max", "medium"),
        ("opus", "xhigh", "medium"),
        ("opus", "low", "medium"),
        ("opus", None, "medium"),
        ("sonnet", "medium", "high"),
        ("sonnet", None, "high"),
        ("fable", "low", "low"),
        ("fable", "medium", "medium"),
        ("fable", "max", "high"),
        ("haiku", "max", "max"),
        ("haiku", None, "medium"),
    ],
)
def test_should_pick_an_allowed_effort(
    effort_levels: dict[str, FamilyEfforts], family: str, effort: object, expected: str
) -> None:
    assert routed_effort(family, effort, effort_levels) == expected


def test_should_set_the_allowed_effort_and_keep_every_other_key(
    effort_levels: dict[str, FamilyEfforts],
) -> None:
    spawn_input = {"model": "opus", "effort": "max", "prompt": "Do X."}
    assert route_spawn_input(spawn_input, None, effort_levels) == (
        {"model": "opus", "effort": "medium", "prompt": "Do X."},
        "opus",
        "medium",
    )


def test_should_use_the_parent_family_when_the_spawn_names_no_model(
    effort_levels: dict[str, FamilyEfforts],
) -> None:
    routed = route_spawn_input({"prompt": "Do X."}, "claude-sonnet-5-5", effort_levels)
    assert routed == ({"prompt": "Do X.", "effort": "high"}, "sonnet", "high")


def test_should_prefer_the_spawn_model_over_the_parent_model(
    effort_levels: dict[str, FamilyEfforts],
) -> None:
    routed = route_spawn_input({"model": "haiku"}, "claude-opus-5-5", effort_levels)
    assert routed == ({"model": "haiku", "effort": "medium"}, "haiku", "medium")


@pytest.mark.parametrize(
    ("tool_input", "parent_model"),
    [
        ({"model": "opus", "effort": "medium"}, None),
        ({"model": "opus", "effort": "high"}, None),
        ({"model": "claude-opus-5-5", "effort": "high"}, None),
        ({"effort": "high"}, "claude-opus-5-5"),
        ({"model": "haiku", "effort": "xhigh"}, None),
        ({"subagent_type": "fork", "effort": "max"}, "claude-opus-5-5"),
        ({"prompt": "Do X."}, None),
        ({"model": "gpt-5", "effort": "max"}, None),
        (["not", "an", "object"], "claude-opus-5-5"),
    ],
)
def test_should_leave_the_spawn_as_it_is(
    effort_levels: dict[str, FamilyEfforts], tool_input: object, parent_model: str | None
) -> None:
    assert route_spawn_input(tool_input, parent_model, effort_levels) is None


def test_should_follow_an_edited_file_with_no_code_change(tmp_path: Path) -> None:
    edited_table = {
        **EFFORT_LEVELS_TABLE,
        "opus": {"allowed": ["xhigh"], "default": "xhigh"},
        "mythos": {"allowed": ["low"], "default": "low"},
    }
    edited_levels = load_effort_levels(_write_levels(tmp_path, json.dumps(edited_table)))
    assert route_spawn_input({"model": "opus", "effort": "high"}, None, edited_levels) == (
        {"model": "opus", "effort": "xhigh"},
        "opus",
        "xhigh",
    )
    assert route_spawn_input({"model": "claude-mythos-1"}, None, edited_levels) == (
        {"model": "claude-mythos-1", "effort": "low"},
        "mythos",
        "low",
    )


def test_should_load_the_shipped_file_with_no_diagnostic(capsys: pytest.CaptureFixture[str]) -> None:
    shipped_levels = load_effort_levels(SHIPPED_EFFORT_LEVELS_PATH)
    assert set(shipped_levels) >= {"opus", "sonnet", "fable", "haiku"}
    assert capsys.readouterr().err == ""


def _table_with(family: str, family_fields: object) -> str:
    return json.dumps({**EFFORT_LEVELS_TABLE, family: family_fields})


def _table_without(family: str) -> str:
    return json.dumps({each_family: each_fields for each_family, each_fields in EFFORT_LEVELS_TABLE.items() if each_family != family})


@pytest.mark.parametrize(
    ("levels_text", "fault_fragment"),
    [
        ("{not json", "Expecting"),
        ("[]", "not an object"),
        ("{}", "not an object"),
        ("[" * 100_000, "recursion"),
        (_table_with("opus", {"allowed": ["turbo"], "default": "turbo"}), "unknown effort 'turbo'"),
        (_table_with("opus", {"allowed": ["medium", "hihg"], "default": "medium"}), "unknown effort 'hihg'"),
        (_table_with("opus", {"allowed": [], "default": "medium"}), "opus allowed"),
        (_table_with("opus", {"allowed": "medium", "default": "medium"}), "opus allowed"),
        (_table_with("opus", {"allowed": ["medium", 5], "default": "medium"}), "opus allowed"),
        (_table_with("opus", {"allowed": ["medium"], "default": 5}), "opus default"),
        (_table_with("opus", {"allowed": ["medium"], "default": "high"}), "opus default"),
        (_table_with("opus", ["medium"]), "'opus'"),
        (_table_with("opus", None), "'opus'"),
        (_table_without("sonnet"), "sonnet"),
    ],
)
def test_should_fall_back_to_the_built_in_levels_with_one_line_naming_the_fault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], levels_text: str, fault_fragment: str
) -> None:
    levels_path = _write_levels(tmp_path, levels_text)
    fallback_levels = load_effort_levels(levels_path)
    assert fallback_levels == load_effort_levels(SHIPPED_EFFORT_LEVELS_PATH)
    assert route_spawn_input({"model": "opus", "effort": "high"}, None, fallback_levels) is None
    assert route_spawn_input({"model": "opus", "effort": "max"}, None, fallback_levels) == (
        {"model": "opus", "effort": "medium"},
        "opus",
        "medium",
    )
    diagnostic_lines = capsys.readouterr().err.splitlines()
    assert len(diagnostic_lines) == 1
    assert str(levels_path) in diagnostic_lines[0]
    assert fault_fragment in diagnostic_lines[0]


def test_should_keep_the_built_in_levels_equal_to_the_shipped_file() -> None:
    shipped_table = json.loads(SHIPPED_EFFORT_LEVELS_PATH.read_text(encoding="utf-8"))
    assert parsed_effort_levels(shipped_table) == parsed_effort_levels(ALL_BUILT_IN_EFFORT_LEVELS_BY_FAMILY)


def test_should_load_the_shipped_file_with_the_default_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert load_effort_levels() == load_effort_levels(SHIPPED_EFFORT_LEVELS_PATH)
    assert capsys.readouterr().err == ""


def test_should_fall_back_when_the_file_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_path = tmp_path / "absent.json"
    fallback_levels = load_effort_levels(missing_path)
    assert route_spawn_input({"model": "sonnet"}, None, fallback_levels) == (
        {"model": "sonnet", "effort": "high"},
        "sonnet",
        "high",
    )
    diagnostic_lines = capsys.readouterr().err.splitlines()
    assert len(diagnostic_lines) == 1
    assert str(missing_path) in diagnostic_lines[0]


def test_should_fall_back_when_the_file_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    levels_path = _write_levels(tmp_path, json.dumps(EFFORT_LEVELS_TABLE))

    def refuse_to_read(*_arguments: object, **_keywords: object) -> str:
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "read_text", refuse_to_read)
    assert load_effort_levels(levels_path) == parsed_effort_levels(ALL_BUILT_IN_EFFORT_LEVELS_BY_FAMILY)
    diagnostic_lines = capsys.readouterr().err.splitlines()
    assert len(diagnostic_lines) == 1
    assert "permission denied" in diagnostic_lines[0]


def test_should_fall_back_at_once_when_the_file_is_a_named_pipe(tmp_path: Path) -> None:
    pipe_path = tmp_path / "subagent_effort_levels.json"
    os.mkfifo(pipe_path)
    completed = subprocess.run(
        [sys.executable, "-c", LOAD_LEVELS_SCRIPT, str(pipe_path)],
        cwd=ROUTING_DIRECTORY,
        capture_output=True,
        text=True,
        check=False,
        timeout=FIFO_RUN_TIMEOUT_SECONDS,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == str(sorted(ALL_BUILT_IN_EFFORT_LEVELS_BY_FAMILY))
    diagnostic_lines = completed.stderr.splitlines()
    assert len(diagnostic_lines) == 1
    assert str(pipe_path) in diagnostic_lines[0]
