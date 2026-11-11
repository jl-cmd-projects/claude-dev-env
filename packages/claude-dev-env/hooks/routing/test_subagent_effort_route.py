import pytest

from subagent_effort_route import model_family, route_spawn_input, routed_effort


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
def test_should_name_the_family_of_a_model(model: object, family: str | None) -> None:
    assert model_family(model) == family


@pytest.mark.parametrize(
    ("family", "effort", "expected"),
    [
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
def test_should_pick_an_allowed_effort(family: str, effort: object, expected: str) -> None:
    assert routed_effort(family, effort) == expected


def test_should_set_the_allowed_effort_and_keep_every_other_key() -> None:
    spawn_input = {"model": "opus", "effort": "high", "prompt": "Do X."}
    assert route_spawn_input(spawn_input, None) == (
        {"model": "opus", "effort": "medium", "prompt": "Do X."},
        "opus",
        "medium",
    )


def test_should_use_the_parent_family_when_the_spawn_names_no_model() -> None:
    routed = route_spawn_input({"prompt": "Do X."}, "claude-sonnet-5-5")
    assert routed == ({"prompt": "Do X.", "effort": "high"}, "sonnet", "high")


def test_should_prefer_the_spawn_model_over_the_parent_model() -> None:
    routed = route_spawn_input({"model": "haiku"}, "claude-opus-5-5")
    assert routed == ({"model": "haiku", "effort": "medium"}, "haiku", "medium")


@pytest.mark.parametrize(
    ("tool_input", "parent_model"),
    [
        ({"model": "opus", "effort": "medium"}, None),
        ({"model": "haiku", "effort": "xhigh"}, None),
        ({"subagent_type": "fork", "effort": "max"}, "claude-opus-5-5"),
        ({"prompt": "Do X."}, None),
        ({"model": "gpt-5", "effort": "max"}, None),
        (["not", "an", "object"], "claude-opus-5-5"),
    ],
)
def test_should_leave_the_spawn_as_it_is(tool_input: object, parent_model: str | None) -> None:
    assert route_spawn_input(tool_input, parent_model) is None
