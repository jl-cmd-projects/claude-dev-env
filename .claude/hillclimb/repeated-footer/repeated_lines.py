"""Count how many times an agent repeats the same line across the replies it sends.

::

    python3 repeated_lines.py <session transcript.jsonl>

Each assistant text block is one reply. Each line of a reply is cut of its
list marker, its spaces are folded, and lines shorter than 16 characters are
left out. A line counts as repeated each time it shows up after a reply that
already sent it::

    reply 1: "Done." + footer of 9 lines      -> 9 new lines
    reply 2: "Nothing is new." + same footer   -> 9 repeated lines
    reply 3: same footer, 1 line reworded      -> 8 repeated lines

The run prints the reply count, the counted line count, how many replies carry
an In progress footer, the repeated line count, and the lines repeated most.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from repeated_footer_eval_support.config.constants import (
    ASSISTANT_RECORD_TYPE,
    CONTENT_KEY,
    HOOKS_DIRECTORY,
    IS_SIDECHAIN_KEY,
    LINE_BREAK,
    LINE_REPORT_TEMPLATE,
    LIST_MARKER_PATTERN,
    MESSAGE_ID_KEY,
    MESSAGE_KEY,
    MINIMUM_COUNTED_LINE_LENGTH,
    RECORD_TYPE_KEY,
    SHOWN_LINE_LENGTH,
    SINGLE_SPACE,
    SPACE_RUN_PATTERN,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TOP_LINE_COUNT,
    TOP_LINE_ROW_TEMPLATE,
    UTF8_ENCODING,
)

blocking_directory = str(HOOKS_DIRECTORY / "blocking")
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from closing_question_round_footer import split_footer

logger = logging.getLogger(__name__)


class RepeatReport(NamedTuple):
    """What a run of replies repeats.

    ::

        two replies that each end with the same 9-line footer
            -> reply_count 2, footer_count 2, repeated_line_count 9

    Attributes:
        reply_count: How many replies were read.
        line_count: How many counted lines the replies hold.
        footer_count: How many replies carry an In progress footer heading.
        repeated_line_count: How many counted lines an earlier reply already sent.
        all_top_lines: The lines sent more than once, most sent first, with their counts.
    """

    reply_count: int
    line_count: int
    footer_count: int
    repeated_line_count: int
    all_top_lines: list[tuple[str, int]]


def counted_lines(reply_text: str) -> list[str]:
    """Return the reply's lines that count, cut of list markers and with spaces folded.

    ::

        "Done.\\n\\nIn progress:\\n- I am shipping pull request 8590."
            -> ["I am shipping pull request 8590."]

    Args:
        reply_text: One reply as the user saw it.

    Returns:
        Each line of 16 or more characters, in reply order.
    """
    all_lines = []
    for each_line in reply_text.split(LINE_BREAK):
        folded_line = SPACE_RUN_PATTERN.sub(
            SINGLE_SPACE, LIST_MARKER_PATTERN.sub("", each_line)
        ).strip()
        if len(folded_line) >= MINIMUM_COUNTED_LINE_LENGTH:
            all_lines.append(folded_line)
    return all_lines


def has_footer(reply_text: str) -> bool:
    """Return True when the reply ends with an In progress footer, as the stop gate reads it.

    ::

        "Done.\n\nIn progress:\n- I am shipping it."                  -> True
        "In progress:\n- I am shipping it.\n\nPick one when back."    -> False

    Args:
        reply_text: One reply as the user saw it.

    Returns:
        Whether the reply ends with the footer.
    """
    return split_footer(reply_text).footer_items is not None


def repeat_report(all_replies: list[str]) -> RepeatReport:
    """Return the repeat counts for replies in the order they were sent.

    ::

        ["A footer line that is long.", "A footer line that is long."]
            -> RepeatReport(2, 2, 0, 1, [("A footer line that is long.", 2)])

    Args:
        all_replies: The replies in the order they were sent.

    Returns:
        The counts, with the five lines that the most replies sent, when more than one reply sent them.
    """
    all_seen_lines: set[str] = set()
    line_counts: Counter[str] = Counter()
    reply_counts: Counter[str] = Counter()
    repeated_line_count = 0
    for each_reply in all_replies:
        all_reply_lines = counted_lines(each_reply)
        repeated_line_count += sum(
            each_line in all_seen_lines for each_line in all_reply_lines
        )
        all_seen_lines.update(all_reply_lines)
        line_counts.update(all_reply_lines)
        reply_counts.update(dict.fromkeys(all_reply_lines, 1))
    all_top_lines = [
        (each_line, each_count)
        for each_line, each_count in reply_counts.most_common(TOP_LINE_COUNT)
        if each_count > 1
    ]
    return RepeatReport(
        reply_count=len(all_replies),
        line_count=sum(line_counts.values()),
        footer_count=sum(has_footer(each_reply) for each_reply in all_replies),
        repeated_line_count=repeated_line_count,
        all_top_lines=all_top_lines,
    )


def transcript_replies(transcript_path: Path) -> list[str]:
    """Return the text of each assistant message in a session transcript, in order.

    Lines that are not JSON objects are skipped, and so are records flagged
    ``isSidechain``, which a subagent wrote and the user never saw. The text
    blocks of records that share one message id join into one reply, so a
    message written across two records counts once.

    Args:
        transcript_path: A session transcript, one JSON record per line.

    Returns:
        The text blocks, in transcript order.
    """
    all_replies: list[str] = []
    reply_position_by_id: dict[str, int] = {}
    for each_line in transcript_path.read_text(encoding=UTF8_ENCODING).splitlines():
        try:
            each_record = json.loads(each_line)
        except ValueError:
            continue
        if (
            not isinstance(each_record, dict)
            or each_record.get(RECORD_TYPE_KEY) != ASSISTANT_RECORD_TYPE
            or each_record.get(IS_SIDECHAIN_KEY)
        ):
            continue
        message_body = each_record.get(MESSAGE_KEY)
        all_blocks = (
            message_body.get(CONTENT_KEY) if isinstance(message_body, dict) else None
        )
        if not isinstance(all_blocks, list):
            continue
        all_texts = [
            each_block[TEXT_KEY]
            for each_block in all_blocks
            if isinstance(each_block, dict)
            and each_block.get(RECORD_TYPE_KEY) == TEXT_BLOCK_TYPE
            and isinstance(each_block.get(TEXT_KEY), str)
        ]
        message_id = message_body.get(MESSAGE_ID_KEY) if isinstance(message_body, dict) else None
        if not isinstance(message_id, str) or not message_id:
            all_replies.extend(all_texts)
            continue
        if not all_texts:
            continue
        if message_id in reply_position_by_id:
            reply_position = reply_position_by_id[message_id]
            all_replies[reply_position] = LINE_BREAK.join([all_replies[reply_position], *all_texts])
            continue
        reply_position_by_id[message_id] = len(all_replies)
        all_replies.append(LINE_BREAK.join(all_texts))
    return all_replies


def report_rows(report: RepeatReport) -> list[str]:
    """Return the summary line, then one row per line sent more than once.

    Args:
        report: The counts to print.

    Returns:
        The rows, summary first.
    """
    return [
        LINE_REPORT_TEMPLATE.format(
            reply_count=report.reply_count,
            line_count=report.line_count,
            footer_count=report.footer_count,
            repeated_line_count=report.repeated_line_count,
        ),
        *(
            TOP_LINE_ROW_TEMPLATE.format(
                count=each_count, line=each_line[:SHOWN_LINE_LENGTH]
            )
            for each_line, each_count in report.all_top_lines
        ),
    ]


def main() -> int:
    """Print the repeat report for one transcript.

    Returns:
        Process exit status, always zero.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "transcript", type=Path, help="A session transcript, one JSON record per line."
    )
    arguments = parser.parse_args()
    for each_row in report_rows(
        repeat_report(transcript_replies(arguments.transcript))
    ):
        logger.info("%s", each_row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
