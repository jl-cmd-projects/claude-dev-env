#!/usr/bin/env python3
"""Score how well the compaction agent hook condenses the user's messages.

::

    python3 compaction_trim_eval.py --reps 3
    deploy_session.jsonl rep 1  facts 13/13  overruled 1/1  ratio 1.6x
    ...
    model: facts 1.00  overruled 1.00  ratio 1.7x  (9 runs)  errors 0
    oracle (raw extract): facts 1.00 ...   null (empty reply): facts 0.00 ...

Each case is a fixture transcript with planted facts: paths, numbers, a
link, and a decision the user later reversed. The runner writes the
extract with ``compaction_user_messages.py``, then sends the agent hook's
own prompt from ``hooks.json`` to ``claude -p`` with the Read tool, the way
Claude Code runs the hook. The grader checks that each fact survives and
that the reversed line says ``overruled``.

The oracle grades the raw extract and the null grades an empty reply, so a
broken grader shows before any model score is trusted. A failed call goes
to the errors list, never to a zero score.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)
_session_directory = str(Path(__file__).resolve().parent)
if _session_directory not in sys.path:
    sys.path.insert(0, _session_directory)

from compaction_user_messages import output_path_for, rendered_extract, typed_user_messages
from hooks_constants.compaction_user_messages_constants import (
    EVAL_ARGUMENTS_PLACEHOLDER,
    EVAL_CASES_FILE_NAME,
    EVAL_CLAUDE_EXECUTABLE,
    EVAL_DEFAULT_MODEL,
    EVAL_FIXTURE_DIRECTORY,
    EVAL_HOOK_TYPE,
    EVAL_HOOKS_JSON_PATH,
    EVAL_JSON_OBJECT_START,
    EVAL_MESSAGE_LINE_PATTERN_TEMPLATE,
    EVAL_OVERRULED_MARKER,
    EVAL_RESULTS_FILE_NAME,
    EVAL_RESULTS_JSON_INDENT,
    EVAL_SERVED_MODEL_SEPARATOR,
    EVAL_SESSION_DIRECTORY,
    EVAL_TIMEOUT_SECONDS,
    EXTRACTOR_SCRIPT_NAME,
    MESSAGES_HEADING,
    OUTPUT_ENCODING,
)


@dataclass(frozen=True)
class CaseScore:
    """One graded condensed copy.

    Attributes:
        facts_kept: Planted facts found in the copy.
        facts_total: Planted facts in the case.
        overruled_marked: Reversed messages whose line says overruled.
        overruled_total: Reversed messages in the case.
        compression_ratio: Extract message characters per copy character.
    """

    facts_kept: int
    facts_total: int
    overruled_marked: int
    overruled_total: int
    compression_ratio: float


@dataclass
class EvalTally:
    """Scores, errors, and per-run records gathered across every case."""

    all_model_scores: list[CaseScore] = field(default_factory=list)
    all_oracle_scores: list[CaseScore] = field(default_factory=list)
    all_null_scores: list[CaseScore] = field(default_factory=list)
    all_errors: list[str] = field(default_factory=list)
    all_records: list[dict[str, object]] = field(default_factory=list)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold()


def _line_for_message(condensed_text: str, position: int) -> str:
    line_pattern = re.compile(
        EVAL_MESSAGE_LINE_PATTERN_TEMPLATE.format(position=position), re.MULTILINE
    )
    found_line = line_pattern.search(condensed_text)
    return found_line.group(0) if found_line else ""


def _overruled_marked(condensed_text: str, all_reversals: list[dict[str, int]]) -> int:
    return sum(
        EVAL_OVERRULED_MARKER
        in _line_for_message(condensed_text, int(each_reversal["earlier"])).casefold()
        for each_reversal in all_reversals
    )


def score_condensed(
    condensed_text: str, all_case_fields: dict[str, object], extract_text: str
) -> CaseScore:
    """Grade one condensed copy against the case's planted facts.

    ::

        "#2 keep Postgres (overruled by #6)" and "#6 switch SQLite"
        -> each fact found case-insensitively, the #2 line marked overruled

    Args:
        condensed_text: The text the hook would return as its reason.
        all_case_fields: One entry from trim_cases.json.
        extract_text: The extract the copy was made from, for the ratio.

    Returns:
        The counts and the compression ratio.
    """
    all_facts = [str(each_fact) for each_fact in all_case_fields["facts"]]
    all_reversals = list(all_case_fields[EVAL_OVERRULED_MARKER])
    normalized_copy = _normalized(condensed_text)
    message_characters = len(extract_text.split(MESSAGES_HEADING, 1)[-1])
    return CaseScore(
        facts_kept=sum(_normalized(each_fact) in normalized_copy for each_fact in all_facts),
        facts_total=len(all_facts),
        overruled_marked=_overruled_marked(condensed_text, all_reversals),
        overruled_total=len(all_reversals),
        compression_ratio=message_characters / max(len(condensed_text), 1),
    )


def condensing_hook_prompt(hooks_json_text: str) -> str:
    """Return the prompt of the PostToolUse agent hook that condenses the messages."""
    all_registrations = json.loads(hooks_json_text)["hooks"]["PostToolUse"]
    return next(
        str(each_hook["prompt"])
        for each_group in all_registrations
        for each_hook in each_group["hooks"]
        if each_hook.get("type") == EVAL_HOOK_TYPE
        and EXTRACTOR_SCRIPT_NAME in str(each_hook.get("if", ""))
    )


def hook_reason(model_reply: str) -> str | None:
    """Return the ``reason`` of the last JSON decision in the reply, or None when there is none."""
    decoder = json.JSONDecoder()
    found_reason = None
    for each_index, each_character in enumerate(model_reply):
        if each_character != EVAL_JSON_OBJECT_START:
            continue
        try:
            decision, _ = decoder.raw_decode(model_reply, each_index)
        except json.JSONDecodeError:
            continue
        if isinstance(decision, dict) and isinstance(decision.get("reason"), str):
            found_reason = decision["reason"]
    return found_reason


def _write_extract(transcript_path: Path) -> tuple[Path, str]:
    all_lines = transcript_path.read_text(encoding=OUTPUT_ENCODING).splitlines()
    extract_text = rendered_extract(typed_user_messages(all_lines))
    extract_path = output_path_for(transcript_path)
    extract_path.write_text(extract_text, encoding=OUTPUT_ENCODING)
    return extract_path, extract_text


def _hook_input(transcript_path: Path, extract_path: Path) -> str:
    command = f"python3 {EVAL_SESSION_DIRECTORY / EXTRACTOR_SCRIPT_NAME} {transcript_path}"
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "tool_response": {"stdout": f"{extract_path}\n", "stderr": "", "interrupted": False},
        }
    )


def _ask_model(prompt_text: str, model_name: str) -> dict[str, object]:
    command = [
        shutil.which(EVAL_CLAUDE_EXECUTABLE) or EVAL_CLAUDE_EXECUTABLE,
        "-p",
        "--model",
        model_name,
        "--setting-sources",
        "",
        "--tools",
        "Read",
        "--allowedTools=Read",
        "--no-session-persistence",
        "--session-id",
        str(uuid.uuid4()),
        "--output-format",
        "json",
    ]
    completed = subprocess.run(
        command,
        input=prompt_text,
        capture_output=True,
        text=True,
        timeout=EVAL_TIMEOUT_SECONDS,
        cwd=tempfile.gettempdir(),
        check=False,
    )
    return json.loads(completed.stdout)


def _run_line(run_label: str, case_score: CaseScore, all_served_models: list[str]) -> str:
    return (
        f"{run_label}  facts {case_score.facts_kept}/{case_score.facts_total}  "
        f"overruled {case_score.overruled_marked}/{case_score.overruled_total}  "
        f"ratio {case_score.compression_ratio:.1f}x  "
        f"served {EVAL_SERVED_MODEL_SEPARATOR.join(all_served_models)}\n"
    )


def _run_once(
    run_label: str,
    prompt_text: str,
    model_name: str,
    all_case_fields: dict[str, object],
    extract_text: str,
    tally: EvalTally,
) -> None:
    try:
        model_output = _ask_model(prompt_text, model_name)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as call_error:
        tally.all_errors.append(f"{run_label}: {type(call_error).__name__}")
        return
    condensed_text = hook_reason(str(model_output.get("result", "")))
    if model_output.get("is_error") or condensed_text is None:
        tally.all_errors.append(f"{run_label}: no reason in reply")
        return
    case_score = score_condensed(condensed_text, all_case_fields, extract_text)
    all_served_models = sorted(dict(model_output.get("modelUsage") or {}))
    tally.all_model_scores.append(case_score)
    tally.all_records.append(
        {
            "run": run_label,
            "served_models": all_served_models,
            "score": case_score.__dict__,
            "condensed": condensed_text,
        }
    )
    sys.stdout.write(_run_line(run_label, case_score, all_served_models))


def _run_case(
    all_case_fields: dict[str, object],
    hook_prompt: str,
    parsed_arguments: argparse.Namespace,
    tally: EvalTally,
) -> None:
    transcript_path = EVAL_FIXTURE_DIRECTORY / str(all_case_fields["transcript"])
    extract_path, extract_text = _write_extract(transcript_path)
    tally.all_oracle_scores.append(score_condensed(extract_text, all_case_fields, extract_text))
    tally.all_null_scores.append(score_condensed("", all_case_fields, extract_text))
    prompt_text = hook_prompt.replace(
        EVAL_ARGUMENTS_PLACEHOLDER, _hook_input(transcript_path, extract_path)
    )
    for each_rep in range(1, parsed_arguments.reps + 1):
        _run_once(
            f"{transcript_path.name} rep {each_rep}",
            prompt_text,
            parsed_arguments.model,
            all_case_fields,
            extract_text,
            tally,
        )


def _summary_line(label: str, all_scores: list[CaseScore]) -> str:
    if not all_scores:
        return f"{label}: no scored runs"
    facts_total = sum(each_score.facts_total for each_score in all_scores)
    facts_share = sum(each_score.facts_kept for each_score in all_scores) / facts_total
    overruled_total = sum(each_score.overruled_total for each_score in all_scores)
    overruled_marked = sum(each_score.overruled_marked for each_score in all_scores)
    overruled_share = overruled_marked / max(overruled_total, 1)
    mean_ratio = sum(each_score.compression_ratio for each_score in all_scores) / len(all_scores)
    return (
        f"{label}: facts {facts_share:.2f}  overruled {overruled_share:.2f}  "
        f"ratio {mean_ratio:.1f}x  ({len(all_scores)} runs)"
    )


def _write_report(tally: EvalTally, output_directory: Path | None) -> None:
    sys.stdout.write(
        _summary_line("model", tally.all_model_scores) + f"  errors {len(tally.all_errors)}\n"
    )
    sys.stdout.write(_summary_line("oracle (raw extract)", tally.all_oracle_scores) + "\n")
    sys.stdout.write(_summary_line("null (empty reply)", tally.all_null_scores) + "\n")
    for each_error in tally.all_errors:
        sys.stdout.write(f"error: {each_error}\n")
    if output_directory is None:
        return
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / EVAL_RESULTS_FILE_NAME).write_text(
        json.dumps(
            {"records": tally.all_records, "errors": tally.all_errors},
            indent=EVAL_RESULTS_JSON_INDENT,
        ),
        encoding=OUTPUT_ENCODING,
    )


def main() -> int:
    """Run every case through the hook prompt, grade it, and print the scores."""
    argument_parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argument_parser.add_argument("--reps", type=int, default=1)
    argument_parser.add_argument("--model", default=EVAL_DEFAULT_MODEL)
    argument_parser.add_argument("--output-dir", type=Path, default=None)
    parsed_arguments = argument_parser.parse_args()
    all_cases = json.loads(
        (EVAL_FIXTURE_DIRECTORY / EVAL_CASES_FILE_NAME).read_text(encoding=OUTPUT_ENCODING)
    )
    hook_prompt = condensing_hook_prompt(EVAL_HOOKS_JSON_PATH.read_text(encoding=OUTPUT_ENCODING))
    tally = EvalTally()
    for each_case in all_cases:
        _run_case(each_case, hook_prompt, parsed_arguments, tally)
    _write_report(tally, parsed_arguments.output_dir)
    return 0 if tally.all_model_scores and not tally.all_errors else 1


if __name__ == "__main__":
    sys.exit(main())
