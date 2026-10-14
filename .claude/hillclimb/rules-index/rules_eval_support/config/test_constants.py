import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2])]

from rules_eval_support.config.constants import FLOW_ROOT, JUDGE_PROMPT_TEMPLATE


def test_flow_root_contains_the_rules_index_cases() -> None:
    assert (FLOW_ROOT / "cases.json").is_file()


def test_judge_prompt_asks_for_a_boolean_verdict() -> None:
    assert '"pass": true or false' in JUDGE_PROMPT_TEMPLATE
