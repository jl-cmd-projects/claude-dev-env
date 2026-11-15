#!/usr/bin/env python3
"""PreToolUse hook that keeps questions for the user out of the files and pages a session sends.

The user answers a question through the question tool's card. A question
inside a sent file or a published page gets no card, and the user may never
see it. So the gate reads each Markdown, text, or HTML file a SendUserFile
call sends, and the page an Artifact publish sends, and denies the call when
the file asks the user something::

    deny:  ## Questions for you                     (a heading that opens a question section)
    deny:  Should I archive the old branches?       (a request for a go-ahead)
    deny:  Do you want the cache cleared first?     (a question that names the reader)
    deny:  Keep it merged, or revert it?            (a choice)
    allow: ## How do I install it?                  (a heading: the answer sits below it)
    allow: Does it retry? No. It fails at once.     (the text answers its own question)
    allow: Can I use it offline? After a sync.      (a frequently asked question and its answer)
    allow: Do you need admin? Only to install.      (the same, worded to the reader)
    allow: > Should we ship this?                   (a quote)
    allow: an Artifact publish that declares db or artifact, such as option cards that save the answer

A question line is a sentence that ends with a question mark (or a full-width
one) and names the reader (you, your), opens with a request (should I, want
me, okay to, proceed, merge, thoughts, are we good, would it make sense,
...), opens with "can I", "could we", or "may I", asks which or what works
best or should be done ("What release date works best?"), or offers a choice
with "or" in ten words or fewer. A list marker and a task box ("- [ ]")
before it are skipped. A checklist item, a list item with a task box or next
to another question item, passes when it only checks the reader's work ("Did
you run the tests?") and asks for no wish, go-ahead, or choice. Headings, a ``summary`` or ``dt`` label, quotes, fenced and
indented code, and preformatted text are not read as questions, except a
heading that opens a question or decision section, such as "Open
questions", "Decisions needed from you", or "Need your input".

A question the next sentence answers with "Yes," "No." and the like passes;
"Yes or no." and "No rush." are no answers. A question that asks for no
wish or go-ahead passes when a statement follows it in the same paragraph or
list item, unless that statement asks for a reply ("Reply yes", "Let me
know"). A wish or go-ahead names the reader with a word such as want,
prefer, like, approve, think, or me, or opens with a request. A "Q:" line
with an "A:" line below it, in the same block or a later one, and a table
cell with an answer cell after it, pass.

A file over 256 KB is read through its first and last 128 KB, and the
refusal, or a system message when the gate lets the call run, says so. A file
that holds a NUL byte or is not UTF-8, and a file the gate cannot read, pass.
The refusal quotes at most 160 characters of the question. The read runs on a
worker thread with a 6 s budget, under the hook's 10 s timeout; when the
budget runs out, the call runs and a system message says the files went
unchecked.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.sent_file_question_gate_constants import (
    ALLOW_EXIT_CODE,
    ALL_ANSWER_SAVING_CAPABILITIES,
    ALL_SKIPPED_PUBLISH_INPUT_KEYS,
    ARTIFACT_ACTION_INPUT_KEY,
    ARTIFACT_CAPABILITIES_INPUT_KEY,
    ARTIFACT_FILE_PATH_INPUT_KEY,
    ARTIFACT_PUBLISH_ACTION,
    ARTIFACT_TOOL_NAME,
    BLOCK_EXIT_CODE,
    CWD_KEY,
    FILE_PATH_SEPARATOR,
    GATE_EVENT_NAME,
    MAXIMUM_QUOTED_CHARACTERS,
    PARTIAL_READ_MESSAGE,
    PARTIAL_READ_NOTE,
    QUESTION_FOUND_MESSAGE,
    QUOTE_CUT_MARK,
    SCAN_BUDGET_SECONDS,
    SCAN_TIMEOUT_MESSAGE,
    SYSTEM_MESSAGE_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)
from open_tasks_transcript_records import send_call_file_paths
from sent_file_question_detector import question_for_user
from sent_file_scan import sent_file_is_partly_read, sent_file_scan_text
from user_step_wording import is_html_file_path


def _short_quote(question: str) -> str:
    if len(question) <= MAXIMUM_QUOTED_CHARACTERS:
        return question
    return question[: MAXIMUM_QUOTED_CHARACTERS - len(QUOTE_CUT_MARK)].rstrip() + QUOTE_CUT_MARK


def _saves_the_answer(all_tool_input_fields: dict[str, object]) -> bool:
    all_capabilities = all_tool_input_fields.get(ARTIFACT_CAPABILITIES_INPUT_KEY)
    if not isinstance(all_capabilities, dict):
        return False
    return not ALL_ANSWER_SAVING_CAPABILITIES.isdisjoint(all_capabilities)


def _published_page_paths(all_tool_input_fields: dict[str, object]) -> list[str]:
    if (
        all_tool_input_fields.get(ARTIFACT_ACTION_INPUT_KEY, ARTIFACT_PUBLISH_ACTION)
        != ARTIFACT_PUBLISH_ACTION
    ):
        return []
    if any(all_tool_input_fields.get(each_key) for each_key in ALL_SKIPPED_PUBLISH_INPUT_KEYS):
        return []
    if _saves_the_answer(all_tool_input_fields):
        return []
    page_path = all_tool_input_fields.get(ARTIFACT_FILE_PATH_INPUT_KEY)
    return [page_path] if isinstance(page_path, str) else []


def sent_file_paths(tool_name: str, all_tool_input_fields: dict[str, object]) -> list[str]:
    """Return the paths of the files a SendUserFile call or an Artifact page publish hands the user.

    >>> sent_file_paths("SendUserFile", {"files": ["a.md", "b.html"]})
    ['a.md', 'b.html']
    >>> sent_file_paths("Artifact", {"file_path": "page.html", "capabilities": {"db": {}}})
    []
    >>> sent_file_paths("Artifact", {"file_path": "page.html", "capabilities": {"sample": {}}})
    ['page.html']

    Args:
        tool_name: The tool the session called.
        all_tool_input_fields: The tool input.

    Returns:
        The paths in call order. An Artifact call that reads, lists, uploads an
        asset, or starts from a type gives none, and so does a publish that
        declares a capability that saves an answer: db, artifact, or self.
    """
    if tool_name == ARTIFACT_TOOL_NAME:
        return _published_page_paths(all_tool_input_fields)
    return send_call_file_paths(tool_name, all_tool_input_fields)


def _sent_file_findings(
    all_file_paths: list[str], working_directory: object
) -> list[tuple[str, str | None, bool]]:
    all_findings: list[tuple[str, str | None, bool]] = []
    for each_path in all_file_paths:
        file_text = sent_file_scan_text(each_path, working_directory)
        if file_text is None:
            continue
        question = question_for_user(file_text, is_html_file_path(each_path))
        is_partly_read = sent_file_is_partly_read(each_path, working_directory)
        all_findings.append((each_path, question, is_partly_read))
        if question is not None:
            break
    return all_findings


def findings_within_budget(
    all_file_paths: list[str], working_directory: object, budget_seconds: float
) -> list[tuple[str, str | None, bool]] | None:
    """Read the sent files on a worker thread, and give up when the budget runs out.

    ::

        two short files          -> [("a.md", None, False), ("b.md", "Should I merge it?", False)]
        a page the parser chews  -> None, after budget_seconds

    The hook command has a 10 s timeout, and a hook that times out lets the
    call run with no word to anyone. A budget below that timeout lets the gate
    say so itself.

    Args:
        all_file_paths: The paths the call sends.
        working_directory: The session's ``cwd`` from the hook payload.
        budget_seconds: How long the read may take.

    Returns:
        One (path, question or None, read only in part) entry per readable
        file, up to the first question, or None when the read did not finish.
    """
    all_results: list[list[tuple[str, str | None, bool]]] = []
    worker = threading.Thread(
        target=lambda: all_results.append(_sent_file_findings(all_file_paths, working_directory)),
        daemon=True,
    )
    worker.start()
    worker.join(budget_seconds)
    return all_results[0] if all_results else None


def _write_system_message(message_text: str) -> None:
    sys.stdout.write(json.dumps({SYSTEM_MESSAGE_KEY: message_text}))


def _reported_findings(all_findings: list[tuple[str, str | None, bool]], tool_name: str) -> int:
    for each_path, each_question, each_is_partly_read in all_findings:
        if each_question is None:
            continue
        block_reason = QUESTION_FOUND_MESSAGE.format(
            file_path=each_path, question=_short_quote(each_question)
        )
        if each_is_partly_read:
            block_reason += PARTIAL_READ_NOTE.format(file_path=each_path)
        log_hook_block(
            Path(__file__).name,
            GATE_EVENT_NAME,
            block_reason,
            tool_name=tool_name,
            offending_input_preview=each_path,
        )
        sys.stderr.write(block_reason)
        return BLOCK_EXIT_CODE
    all_partly_read_paths = [
        each_path
        for each_path, _each_question, each_is_partly_read in all_findings
        if each_is_partly_read
    ]
    if all_partly_read_paths:
        _write_system_message(
            PARTIAL_READ_MESSAGE.format(file_paths=FILE_PATH_SEPARATOR.join(all_partly_read_paths))
        )
    return ALLOW_EXIT_CODE


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    all_file_paths = sent_file_paths(tool_name, tool_input)
    if not all_file_paths:
        return ALLOW_EXIT_CODE
    all_findings = findings_within_budget(
        all_file_paths, hook_input.get(CWD_KEY), SCAN_BUDGET_SECONDS
    )
    if all_findings is None:
        _write_system_message(
            SCAN_TIMEOUT_MESSAGE.format(
                file_paths=FILE_PATH_SEPARATOR.join(all_file_paths),
                budget_seconds=SCAN_BUDGET_SECONDS,
            )
        )
        return ALLOW_EXIT_CODE
    return _reported_findings(all_findings, tool_name)


if __name__ == "__main__":
    sys.exit(main())
