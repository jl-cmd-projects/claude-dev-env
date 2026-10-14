from rules_eval_support.config.constants import (
    ALL_SCORABLE_SUBTYPES,
    FLOW_ROOT,
    JUDGE_PROMPT_TEMPLATE,
    JUDGE_VERDICT_PATTERN,
)


def test_flow_root_contains_the_rules_index_cases() -> None:
    assert (FLOW_ROOT / "cases.json").is_file()


def test_judge_contract_has_a_boolean_verdict_and_scored_session_types() -> None:
    assert '"pass": true or false' in JUDGE_PROMPT_TEMPLATE
    assert JUDGE_VERDICT_PATTERN.findall('before {"pass": true} after') == [
        '{"pass": true}'
    ]
    assert ALL_SCORABLE_SUBTYPES == {"success", "error_max_turns"}
