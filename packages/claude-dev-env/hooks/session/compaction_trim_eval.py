#!/usr/bin/env python3
"""Score how well the Python trim keeps the user's messages after a compaction.

::

    python3 compaction_trim_eval.py
    deploy_session.jsonl  facts 13/13  overruled 1/1  ratio 1.6x
    ...
    trim: facts 1.00  overruled 1.00  ratio 1.7x  (4 cases)
    oracle (raw messages): facts 1.00 ...   null (empty recall): facts 0.00 ...

Each case is a fixture transcript with planted facts: paths, numbers, a
link, and a decision the user later reversed. The eval trims the fixture's
typed messages exactly as the SessionStart hook does, then checks that each
fact survives and that each reversed message's line says ``overruled``.

The oracle grades the raw messages and the null grades an empty recall, so a
broken grader shows before the trim score is trusted. The eval exits 1 when
the trim loses a fact or leaves a reversal unmarked.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)
_session_directory = str(Path(__file__).resolve().parent)
if _session_directory not in sys.path:
    sys.path.insert(0, _session_directory)

from compaction_trim import recall_text
from compaction_user_messages import typed_user_messages
from hooks_constants.compaction_user_messages_constants import (
    EVAL_CASE_EARLIER_KEY,
    EVAL_CASE_FACTS_KEY,
    EVAL_CASE_OVERRULED_KEY,
    EVAL_CASE_TRANSCRIPT_KEY,
    EVAL_CASES_FILE_NAME,
    EVAL_FILE_ENCODING,
    EVAL_FIXTURE_DIRECTORY,
    EVAL_MESSAGE_LINE_PATTERN_TEMPLATE,
    EVAL_OVERRULED_MARKER,
    LINE_SEPARATOR,
)


@dataclass(frozen=True)
class CaseScore:
    """One graded recall.

    Attributes:
        facts_kept: Planted facts found in the recall.
        facts_total: Planted facts in the case.
        overruled_marked: Reversed messages whose line says overruled.
        overruled_total: Reversed messages in the case.
        compression_ratio: Raw message characters per recall character.
    """

    facts_kept: int
    facts_total: int
    overruled_marked: int
    overruled_total: int
    compression_ratio: float

    @property
    def is_lossless(self) -> bool:
        """True when every fact survives and every reversal is marked."""
        return (
            self.facts_kept == self.facts_total
            and self.overruled_marked == self.overruled_total
        )


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold()


def _line_for_message(recall: str, position: int) -> str:
    line_pattern = re.compile(
        EVAL_MESSAGE_LINE_PATTERN_TEMPLATE.format(position=position), re.MULTILINE
    )
    found_line = line_pattern.search(recall)
    return found_line.group(0) if found_line else ""


def _overruled_marked(recall: str, all_reversals: list[dict[str, int]]) -> int:
    return sum(
        EVAL_OVERRULED_MARKER
        in _line_for_message(recall, int(each_reversal[EVAL_CASE_EARLIER_KEY])).casefold()
        for each_reversal in all_reversals
    )


def score_condensed(
    recall: str, all_case_fields: dict[str, object], raw_messages: str
) -> CaseScore:
    """Grade one recall against the case's planted facts.

    ::

        "#2 keep Postgres (overruled by #6)" and "#6 switch SQLite"
        -> each fact found case-insensitively, the #2 line marked overruled

    Args:
        recall: The trimmed lines the hook would return.
        all_case_fields: One entry from trim_cases.json.
        raw_messages: The typed messages the recall was made from, for the ratio.

    Returns:
        The counts and the compression ratio.
    """
    all_facts = [str(each_fact) for each_fact in all_case_fields[EVAL_CASE_FACTS_KEY]]
    all_reversals = list(all_case_fields[EVAL_CASE_OVERRULED_KEY])
    normalized_recall = _normalized(recall)
    return CaseScore(
        facts_kept=sum(_normalized(each_fact) in normalized_recall for each_fact in all_facts),
        facts_total=len(all_facts),
        overruled_marked=_overruled_marked(recall, all_reversals),
        overruled_total=len(all_reversals),
        compression_ratio=len(raw_messages) / max(len(recall), 1),
    )


def _scored_case(
    fixture_directory: Path, all_case_fields: dict[str, object]
) -> tuple[str, CaseScore, CaseScore, CaseScore]:
    transcript_name = str(all_case_fields[EVAL_CASE_TRANSCRIPT_KEY])
    transcript_text = (fixture_directory / transcript_name).read_text(encoding=EVAL_FILE_ENCODING)
    all_messages = typed_user_messages(transcript_text.splitlines())
    raw_messages = LINE_SEPARATOR.join(each_message.text for each_message in all_messages)
    recall = recall_text(all_messages) or ""
    return (
        transcript_name,
        score_condensed(recall, all_case_fields, raw_messages),
        score_condensed(raw_messages, all_case_fields, raw_messages),
        score_condensed("", all_case_fields, raw_messages),
    )


def scored_cases(fixture_directory: Path) -> list[tuple[str, CaseScore, CaseScore, CaseScore]]:
    """Trim every case's transcript and grade it beside the oracle and the null.

    ::

        trim_cases.json with deploy_session.jsonl
        -> [("deploy_session.jsonl", trim score, oracle score, null score)]

    Args:
        fixture_directory: The folder that holds trim_cases.json and its transcripts.

    Returns:
        One row per case: its transcript name, then the trim, oracle, and null scores.
    """
    all_cases = json.loads(
        (fixture_directory / EVAL_CASES_FILE_NAME).read_text(encoding=EVAL_FILE_ENCODING)
    )
    return [_scored_case(fixture_directory, each_case) for each_case in all_cases]


def _summary_line(label: str, all_scores: list[CaseScore]) -> str:
    facts_total = sum(each_score.facts_total for each_score in all_scores)
    facts_share = sum(each_score.facts_kept for each_score in all_scores) / max(facts_total, 1)
    overruled_total = sum(each_score.overruled_total for each_score in all_scores)
    overruled_marked = sum(each_score.overruled_marked for each_score in all_scores)
    overruled_share = overruled_marked / max(overruled_total, 1)
    mean_ratio = sum(each_score.compression_ratio for each_score in all_scores) / max(
        len(all_scores), 1
    )
    return (
        f"{label}: facts {facts_share:.2f}  overruled {overruled_share:.2f}  "
        f"ratio {mean_ratio:.1f}x  ({len(all_scores)} cases)\n"
    )


def main() -> int:
    """Grade the trim on every fixture case, print the scores, and exit 1 on any loss."""
    all_rows = scored_cases(EVAL_FIXTURE_DIRECTORY)
    for each_name, each_score, _, _ in all_rows:
        sys.stdout.write(
            f"{each_name}  facts {each_score.facts_kept}/{each_score.facts_total}  "
            f"overruled {each_score.overruled_marked}/{each_score.overruled_total}  "
            f"ratio {each_score.compression_ratio:.1f}x\n"
        )
    all_trim_scores = [each_row[1] for each_row in all_rows]
    sys.stdout.write(_summary_line("trim", all_trim_scores))
    sys.stdout.write(_summary_line("oracle (raw messages)", [each_row[2] for each_row in all_rows]))
    sys.stdout.write(_summary_line("null (empty recall)", [each_row[3] for each_row in all_rows]))
    return 0 if all_trim_scores and all(each.is_lossless for each in all_trim_scores) else 1


if __name__ == "__main__":
    sys.exit(main())
