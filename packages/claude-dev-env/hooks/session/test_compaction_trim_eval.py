"""Tests for compaction_trim_eval: the grader, the hook settings, and the reason parsers."""

import json
import sys
from pathlib import Path

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import compaction_trim_eval as trim_eval
from compaction_user_messages import rendered_extract, typed_user_messages

DEPLOY_CASE = {
    "transcript": "deploy_session.jsonl",
    "facts": ["batch-07.internal", "137", "SQLite"],
    "overruled": [{"earlier": 2, "later": 6}],
}
EXTRACT_TEXT = "# User messages, oldest first\n\n" + "m" * 400


def test_score_condensed_should_count_every_fact_and_the_marked_reversal() -> None:
    condensed_text = (
        "#1 deploy to BATCH-07.internal\n#2 keep Postgres (overruled by #6)\n"
        "#5 exit code 137\n#6 switch to SQLite\n"
    )
    case_score = trim_eval.score_condensed(condensed_text, DEPLOY_CASE, EXTRACT_TEXT)
    assert (case_score.facts_kept, case_score.facts_total) == (3, 3)
    assert (case_score.overruled_marked, case_score.overruled_total) == (1, 1)
    assert case_score.compression_ratio == len("m" * 400) / len(condensed_text)


def test_score_condensed_should_score_a_copy_that_drops_facts_lower() -> None:
    lossy_text = "#1 deploy\n#2 keep Postgres\n#6 switch db\n"
    case_score = trim_eval.score_condensed(lossy_text, DEPLOY_CASE, EXTRACT_TEXT)
    assert case_score.facts_kept == 0
    assert case_score.overruled_marked == 0


def test_score_condensed_should_give_the_raw_extract_every_fact_and_an_empty_copy_none() -> None:
    fixture_directory = _SESSION_DIR / "fixtures" / "compaction_user_messages"
    all_cases = json.loads((fixture_directory / "trim_cases.json").read_text(encoding="utf-8"))
    for each_case in all_cases:
        transcript_lines = (fixture_directory / each_case["transcript"]).read_text().splitlines()
        extract_text = rendered_extract(typed_user_messages(transcript_lines))
        oracle_score = trim_eval.score_condensed(extract_text, each_case, extract_text)
        null_score = trim_eval.score_condensed("", each_case, extract_text)
        assert oracle_score.facts_kept == oracle_score.facts_total
        assert null_score.facts_kept == 0


CONDENSING_HOOK = {
    "type": "agent",
    "if": "Bash(*compaction_user_messages.py*)",
    "prompt": "condense $ARGUMENTS",
    "model": "haiku",
}


def test_condensing_hook_group_should_keep_only_the_agent_hook_that_names_the_extractor() -> None:
    hooks_json_text = json.dumps(
        {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]},
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "y"}, CONDENSING_HOOK],
                    },
                ]
            }
        }
    )
    assert trim_eval.condensing_hook_group(hooks_json_text) == {
        "matcher": "Bash",
        "hooks": [CONDENSING_HOOK],
    }


def test_run_settings_should_register_the_hook_on_the_chosen_model_with_the_allow_rules() -> None:
    hook_group = {"matcher": "Bash", "hooks": [CONDENSING_HOOK]}
    all_allow_rules = ["Read(~/.claude/compaction-recall/**)"]
    assert trim_eval.run_settings(hook_group, all_allow_rules, "sonnet") == {
        "permissions": {"allow": all_allow_rules},
        "hooks": {
            "PostToolUse": [{"matcher": "Bash", "hooks": [{**CONDENSING_HOOK, "model": "sonnet"}]}]
        },
    }


def test_debug_log_reason_should_return_the_last_structured_output_reason() -> None:
    debug_text = (
        "2026 [DEBUG] Hooks: Processing agent hook with prompt: condense\n"
        '2026 [DEBUG] Hooks: Got structured output: {"ok":false,"reason":"draft"}\n'
        '2026 [DEBUG] Hooks: Got structured output: {"ok":false,"reason":"#1 deploy\\n#2 keep"}\n'
    )
    assert trim_eval.debug_log_reason(debug_text) == "#1 deploy\n#2 keep"


def test_debug_log_reason_should_return_none_when_no_hook_answered() -> None:
    assert trim_eval.debug_log_reason("2026 [DEBUG] Read tool permission denied\n") is None


def test_hook_reason_should_return_the_last_decision_with_a_reason() -> None:
    model_reply = (
        'Draft {"ok": false, "reason": "first"} then {"note": 1} and '
        '{"ok": false, "reason": "#1 use {braces} here"}'
    )
    assert trim_eval.hook_reason(model_reply) == "#1 use {braces} here"


def test_hook_reason_should_return_none_when_the_reply_has_no_decision() -> None:
    assert trim_eval.hook_reason("I could not read the file {broken") is None
