from pathlib import Path
import sys

SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from tools.config import efficient_review_constants as constants
from tools.efficient_review_plan import plan_review


def test_host_markers_select_the_claude_plan_only_on_claude() -> None:
    claude_plan = plan_review({constants.ALL_CLAUDE_HOST_VARIABLES[0]: "1"})
    other_plan = plan_review(
        {
            constants.ALL_CLAUDE_HOST_VARIABLES[0]: "1",
            constants.ALL_OTHER_HOST_VARIABLES[0]: "1",
        }
    )

    assert claude_plan["runtime"] == "claude"
    assert claude_plan["model"] == "haiku"
    assert other_plan == {"runtime": "other", "model": "deferred", "profile": "deferred"}
