"""The plan selects haiku on Claude and defers the model on every other runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from tools.config import efficient_review_constants as c
from tools.efficient_review_plan import plan_review


def test_should_load_the_slim_profile_from_the_claude_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_root = tmp_path / ".agents" / "skills" / "efficient-review"
    skill_root.mkdir(parents=True)
    constants_path = (
        tmp_path
        / ".claude"
        / "hooks"
        / "hooks_constants"
        / c.GATE_CONSTANTS_FILENAME
    )
    constants_path.parent.mkdir(parents=True)
    source = (
        SKILL_ROOT.parents[2]
        / "hooks"
        / "hooks_constants"
        / c.GATE_CONSTANTS_FILENAME
    )
    constants_path.write_text(source.read_text(encoding=c.TEXT_ENCODING), encoding=c.TEXT_ENCODING)
    monkeypatch.setattr(c, "SKILL_ROOT", skill_root)
    plan = plan_review({"CLAUDECODE": "1"})
    assert plan["model"] == "haiku"
    assert plan["profile"] == "slim"


FORBIDDEN_SNIPPETS = (
    "dispatch_repository",
    "dispatch_workflow",
    "dispatch_ref",
    "read_token",
    "results_branch",
    "account_broker",
    "urllib",
    "socket",
)


def test_should_select_haiku_and_the_slim_profile_on_claude() -> None:
    plan = plan_review({"CLAUDECODE": "1"})
    assert plan["runtime"] == "claude"
    assert plan["model"] == "haiku"
    assert plan["profile"] == "slim"
    assert plan["command"][0] == "claude"
    assert "--model" in plan["command"]
    assert plan["command"][plan["command"].index("--model") + 1] == "haiku"
    assert "CLAUDE_CODE_DISABLE_CLAUDE_MDS=1" in plan["environment"]
    serialized = json.dumps(plan)
    assert "token" not in serialized
    assert "dispatch" not in serialized


def test_should_defer_the_model_when_the_runtime_is_not_claude() -> None:
    for each_environment in (
        {},
        {"CURSOR_AGENT": "1"},
        {"CODEX_HOME": "/tmp/codex"},
        {"CURSOR_AGENT": "1", "CLAUDECODE": "1"},
    ):
        plan = plan_review(each_environment)
        assert plan == {
            "runtime": "other",
            "model": "deferred",
            "profile": "deferred",
        }


def test_should_keep_dispatch_and_network_out_of_the_skill() -> None:
    all_texts = [
        each_path.read_text(encoding=c.TEXT_ENCODING)
        for each_path in SKILL_ROOT.rglob("*.py")
        if "tests" not in each_path.parts
    ]
    combined = "\n".join(all_texts)
    for each_snippet in FORBIDDEN_SNIPPETS:
        assert each_snippet not in combined
