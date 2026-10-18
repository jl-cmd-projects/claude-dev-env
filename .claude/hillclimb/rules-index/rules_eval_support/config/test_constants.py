import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(flow_directory), str(flow_directory.parent / "features-start-with-an-eval")]

from rules_eval_support.config.constants import FLOW_ROOT, JUDGE_PROMPT_TEMPLATE
from rules_eval_support.judge import parse_verdict


def test_flow_root_contains_the_rules_index_cases() -> None:
    assert (FLOW_ROOT / "cases.json").is_file()


def test_the_reply_shape_the_judge_prompt_asks_for_parses_as_a_verdict() -> None:
    asked_reply = JUDGE_PROMPT_TEMPLATE.rsplit("nothing else: ", 1)[1].replace("{{", "{").replace("}}", "}")
    filled_reply = asked_reply.replace("true or false", "false").replace("<one sentence>", "Skipped the guide.")

    assert parse_verdict(filled_reply) == {"pass": False, "reason": "Skipped the guide."}
