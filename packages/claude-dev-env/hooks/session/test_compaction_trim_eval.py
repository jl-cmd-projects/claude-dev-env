"""Tests for compaction_trim_eval: the grader and the fixture cases it scores."""

import json
import sys
from pathlib import Path

import pytest

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import compaction_trim_eval as trim_eval

FIXTURE_DIRECTORY = _SESSION_DIR / "fixtures" / "compaction_user_messages"
DEPLOY_CASE = {
    "transcript": "deploy_session.jsonl",
    "facts": ["batch-07.internal", "137", "SQLite"],
    "overruled": [{"earlier": 2, "later": 6}],
}
RAW_MESSAGES = "m" * 400


def test_score_condensed_should_count_every_fact_and_the_marked_reversal() -> None:
    recall = (
        "#1 deploy to BATCH-07.internal\n#2 keep Postgres (overruled by #6)\n"
        "#5 exit code 137\n#6 switch to SQLite\n"
    )
    case_score = trim_eval.score_condensed(recall, DEPLOY_CASE, RAW_MESSAGES)
    assert (case_score.facts_kept, case_score.facts_total) == (3, 3)
    assert (case_score.overruled_marked, case_score.overruled_total) == (1, 1)
    assert case_score.compression_ratio == len(RAW_MESSAGES) / len(recall)
    assert case_score.is_lossless


def test_score_condensed_should_score_a_recall_that_drops_facts_lower() -> None:
    lossy_recall = "#1 deploy\n#2 keep Postgres\n#6 switch db\n"
    case_score = trim_eval.score_condensed(lossy_recall, DEPLOY_CASE, RAW_MESSAGES)
    assert case_score.facts_kept == 0
    assert case_score.overruled_marked == 0
    assert not case_score.is_lossless


def test_scored_cases_should_keep_every_fact_and_reversal_in_each_fixture() -> None:
    all_cases = json.loads((FIXTURE_DIRECTORY / "trim_cases.json").read_text(encoding="utf-8"))
    all_rows = trim_eval.scored_cases(FIXTURE_DIRECTORY)
    assert [each_row[0] for each_row in all_rows] == [
        each_case["transcript"] for each_case in all_cases
    ]
    for each_name, trim_score, oracle_score, null_score in all_rows:
        assert trim_score.is_lossless, each_name
        assert oracle_score.facts_kept == oracle_score.facts_total, each_name
        assert null_score.facts_kept == 0, each_name


def test_main_should_exit_zero_when_the_trim_keeps_every_fact(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert trim_eval.main() == 0
    assert "trim: facts 1.00  overruled 1.00" in capsys.readouterr().out
