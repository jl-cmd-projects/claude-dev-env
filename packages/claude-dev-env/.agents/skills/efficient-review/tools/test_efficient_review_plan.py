from pathlib import Path
import sys

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from tools.efficient_review_plan import plan_review


def test_claude_plan_supplies_the_headless_slim_profile() -> None:
    plan = plan_review({"CLAUDECODE": "1"})

    assert plan["runtime"] == "claude"
    assert plan["model"] == "haiku"
    assert plan["profile"] == "slim"
    assert plan["command"][:3] == ["claude", "-p", "--model"]
    assert "--strict-mcp-config" in plan["command"]
    assert "CLAUDE_CODE_DISABLE_CLAUDE_MDS=1" in plan["environment"]


def test_other_host_takes_priority_over_claude_marker() -> None:
    assert plan_review({"CLAUDECODE": "1", "CODEX_CI": "1"}) == {
        "runtime": "other",
        "model": "deferred",
        "profile": "deferred",
    }
