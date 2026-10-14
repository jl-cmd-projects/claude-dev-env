#!/usr/bin/env python3
"""Score arena runs and print one results table.

Usage::

    python3 score_arena.py --runs /path/to/runs [--judge-model sonnet] [--no-judge]

Per run, the scorer reads ``stream.jsonl``, ``display.jsonl``, and
``helper.jsonl`` and computes these metrics::

    replies shown     text messages after the last tool result, as the hooks logged them
    one reply only    replies shown == 1
    visible words     words in every text message the user saw in the turn, narration included
    first pass        reply_violation on the first text message after the last tool result
    shown pass        reply_violation on the last text message the user saw
    correct           judge model says the text the user saw after the last tool keeps the key outcome
    seconds, cost     wall time, and the agent cost plus helper cost in dollars

The judge sees the prompt, the key outcome, and only the text the user saw.
Its verdict is cached in ``judge.json`` inside the run folder.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

package_directory = Path(__file__).resolve().parents[2] / "packages" / "claude-dev-env"
for each_path in (
    package_directory / "hooks",
    package_directory / "hooks" / "blocking",
):
    if str(each_path) not in sys.path:
        sys.path.insert(0, str(each_path))

from reply_length_gate import reply_violation

JUDGE_TIMEOUT_SECONDS = 120
JUDGE_SYSTEM_PROMPT = (
    "You grade whether a short chat reply keeps the correct outcome for the user's question."
    " Short replies leave out detail; that is fine. Answer 1 when the reply gives the central answer"
    " named in the key outcome, or a correct recommendation consistent with it, and states nothing false."
    " Answer 0 when the central answer is missing or wrong, or the reply states something false."
    ' Reply with JSON only, in the form {"correct": 0 or 1, "why": "one short sentence"}.'
)


def read_jsonl(file_path: Path) -> list[dict[str, object]]:
    """Return the JSON objects in a JSONL file, skipping lines that do not parse."""
    if not file_path.exists():
        return []
    all_records = []
    for each_line in file_path.read_text(encoding="utf-8").splitlines():
        try:
            all_records.append(json.loads(each_line))
        except json.JSONDecodeError:
            continue
    return all_records


def stream_summary(all_events: list[dict[str, object]]) -> tuple[list[str], int, float]:
    """Return the text messages in order, how many came after the last tool use, and the agent cost."""
    all_cost_events = [each_event for each_event in all_events if each_event.get("type") == "result"]
    agent_cost = float(all_cost_events[-1].get("total_cost_usd") or 0.0) if all_cost_events else 0.0
    all_blocks = [
        (str(each_event["message"].get("id")), each_block)
        for each_event in all_events
        if each_event.get("type") == "assistant" and not each_event.get("parent_tool_use_id")
        for each_block in each_event["message"].get("content") or []
    ]
    texts_by_message: dict[str, list[str]] = {}
    texts_before_last_tool = 0
    for each_message_id, each_block in all_blocks:
        if each_block.get("type") == "tool_use":
            texts_before_last_tool = len(texts_by_message)
        if each_block.get("type") == "text" and each_block.get("text", "").strip():
            texts_by_message.setdefault(each_message_id, []).append(each_block["text"])
    all_texts = ["".join(each_parts) for each_parts in texts_by_message.values()]
    return all_texts, len(all_texts) - texts_before_last_tool, agent_cost


def judge(
    run_directory: Path,
    prompt_record: dict[str, str],
    shown_reply: str,
    judge_model: str,
) -> int | None:
    """Return the cached or fresh 0/1 correctness verdict for the text the user saw."""
    cache_path = run_directory / "judge.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")).get("correct")
    request_text = (
        f"Question: {prompt_record['prompt']}\n\nKey outcome: {prompt_record['key']}\n\n"
        f"Reply the user saw:\n\n{shown_reply}"
    )
    command = [
        "claude",
        "-p",
        "--model",
        judge_model,
        "--setting-sources",
        "",
        "--tools",
        "",
        "--no-session-persistence",
        "--session-id",
        str(uuid.uuid4()),
        "--output-format",
        "json",
        "--system-prompt",
        JUDGE_SYSTEM_PROMPT,
    ]
    try:
        completed = subprocess.run(
            command,
            input=request_text,
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT_SECONDS,
            check=False,
        )
        result_text = json.loads(completed.stdout).get("result", "")
        verdict = json.loads(
            result_text[result_text.find("{") : result_text.rfind("}") + 1]
        )
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return None
    cache_path.write_text(json.dumps(verdict), encoding="utf-8")
    return verdict.get("correct")


def word_count(text: str) -> int:
    """Return the whitespace word count of a text."""
    return len(text.split())


def score_run(
    run_directory: Path, prompt_record: dict[str, str], judge_model: str | None
) -> dict[str, object]:
    """Return the metrics for one run folder."""
    meta = json.loads((run_directory / "meta.json").read_text(encoding="utf-8"))
    all_texts, final_text_count, agent_cost = stream_summary(
        read_jsonl(run_directory / "stream.jsonl")
    )
    all_display_records = read_jsonl(run_directory / "display.jsonl")
    all_helper_records = read_jsonl(run_directory / "helper.jsonl")
    is_display_aligned = len(all_display_records) == len(all_texts)
    all_shown_texts = (
        [str(each_record.get("shown") or "") for each_record in all_display_records]
        if is_display_aligned
        else all_texts
    )
    all_original_texts = (
        [str(each_record.get("original") or "") for each_record in all_display_records]
        if is_display_aligned
        else all_texts
    )
    final_start = len(all_texts) - final_text_count
    final_shown_texts = all_shown_texts[final_start:] if final_text_count else []
    final_original_texts = all_original_texts[final_start:] if final_text_count else []
    first_reply = final_original_texts[0] if final_original_texts else ""
    last_shown = final_shown_texts[-1] if final_shown_texts else ""
    shown_reply = "\n\n".join(final_shown_texts)
    correct = (
        None
        if judge_model is None
        else judge(run_directory, prompt_record, shown_reply, judge_model)
    )
    return {
        "contender": meta["contender"],
        "prompt_id": meta["prompt_id"],
        "replies_shown": final_text_count,
        "display_aligned": is_display_aligned,
        "visible_words": sum(word_count(each_text) for each_text in all_shown_texts),
        "first_pass": reply_violation(first_reply, None, None) is None,
        "shown_pass": reply_violation(last_shown, None, None) is None,
        "correct": correct,
        "seconds": meta["seconds"],
        "cost_usd": agent_cost
        + sum(
            float(each_record.get("cost_usd") or 0.0)
            for each_record in all_helper_records
        ),
        "helper_calls": len(all_helper_records),
    }


def summarize(all_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return one summary row per contender."""
    all_summaries = []
    for each_contender in sorted({str(each_row["contender"]) for each_row in all_rows}):
        rows = [
            each_row for each_row in all_rows if each_row["contender"] == each_contender
        ]
        judged = [
            each_row["correct"] for each_row in rows if each_row["correct"] is not None
        ]
        run_count = len(rows)
        all_summaries.append(
            {
                "contender": each_contender,
                "runs": run_count,
                "one_reply_pct": round(
                    100
                    * sum(each_row["replies_shown"] == 1 for each_row in rows)
                    / run_count
                ),
                "mean_visible_words": round(
                    sum(each_row["visible_words"] for each_row in rows) / run_count, 1
                ),
                "first_pass_pct": round(
                    100
                    * sum(bool(each_row["first_pass"]) for each_row in rows)
                    / run_count
                ),
                "shown_pass_pct": round(
                    100
                    * sum(bool(each_row["shown_pass"]) for each_row in rows)
                    / run_count
                ),
                "correct_pct": round(100 * sum(judged) / len(judged))
                if judged
                else None,
                "mean_seconds": round(
                    sum(each_row["seconds"] for each_row in rows) / run_count, 1
                ),
                "mean_cost_usd": round(
                    sum(each_row["cost_usd"] for each_row in rows) / run_count, 3
                ),
                "helper_calls": sum(each_row["helper_calls"] for each_row in rows),
            }
        )
    return all_summaries


def markdown_table(all_summaries: list[dict[str, object]]) -> str:
    """Return the summary rows as a markdown table."""
    all_columns = list(all_summaries[0])
    all_lines = ["| " + " | ".join(all_columns) + " |", "|" + "---|" * len(all_columns)]
    all_lines += [
        "| "
        + " | ".join(str(each_row[each_column]) for each_column in all_columns)
        + " |"
        for each_row in all_summaries
    ]
    return "\n".join(all_lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--judge-model", default="sonnet")
    parser.add_argument("--no-judge", action="store_true")
    arguments = parser.parse_args()
    all_prompts = {
        each_prompt["id"]: each_prompt
        for each_prompt in json.loads(
            (Path(__file__).resolve().parent / "prompts.json").read_text(
                encoding="utf-8"
            )
        )
    }
    judge_model = None if arguments.no_judge else arguments.judge_model
    all_rows = [
        score_run(each_meta.parent, all_prompts[each_meta.parent.name], judge_model)
        for each_meta in sorted(arguments.runs.rglob("meta.json"))
    ]
    (arguments.runs / "rows.json").write_text(
        json.dumps(all_rows, indent=1), encoding="utf-8"
    )
    print(markdown_table(summarize(all_rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
