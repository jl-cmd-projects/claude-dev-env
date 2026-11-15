#!/usr/bin/env python3
"""PermissionDenied advisor: a proposed quick fix for each auto mode denial.

This hook never retries the denied call. It reads the denial's ``reason``,
names the classifier rule, drafts one ``autoMode.allow`` entry for the denied
action, and adds a PowerShell 7 block that writes the entry to
``~/.claude/settings.json`` with ``"$defaults"`` kept. The agent receives the
proposal as ``additionalContext``; the user receives a one-line
``systemMessage``.

A ``reason`` that says auto mode could not evaluate the action, that the
classifier was unavailable or gave no verdict, that a hook changed the input
after review, or that is not text has no verdict. It gets a short note and no
block, because an allow entry cannot clear it.

The ``reason`` can echo text from a web page or a file. A rule label keeps
only ASCII letters, digits, spaces, ``-``, ``_`` and ``/``, and every quote
form PowerShell reads as a single quote is doubled where text enters a
single-quoted literal.

When ``CLAUDE_AUTO_MODE_RULE_PLAYBOOK`` names an existing file, the hook also
keeps the refusal ledger::

    labelled refusal    -> one ledger entry per distinct step, the group's
                           question record, and the exact question appended
                           to the agent's context
    unexplained danger  -> the same, under the rule label ``Unexplained``
    anything else       -> today's output and no ledger file

An unexplained danger reason starts ``The server-side auto mode classifier
judged this action dangerous``. It first reads the user's answers from
``transcript_path``. It writes no entry for any other reason with no rule
label, or for one of the rule flow's own
steps, which ``auto_mode_rule_steps.py`` names: a Bash command that runs
``setup/add_auto_mode_rule.py``, or, once the session holds an allowed entry,
a Bash ``git commit`` or ``git push`` of a ``claude/auto-mode-rule-`` branch
in the playbook's repository or one of its worktrees. Any ledger or
transcript error, and a playbook with no repository folder above it, gives
today's output.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_root_directory not in sys.path:
    sys.path.insert(0, _hooks_root_directory)

import auto_mode_refusal_ledger
from hooks_constants.auto_mode_denial_quick_fix_constants import (
    ALL_COMMAND_INPUT_KEYS,
    ALL_NO_VERDICT_REASON_PREFIXES,
    ALL_POWERSHELL_SINGLE_QUOTE_CHARACTERS,
    ALLOW_ENTRY_TEMPLATE,
    BARE_LABEL_PATTERN,
    BRACKETED_LABEL_PATTERN,
    CLASSIFIER_REASON_PREFIX_PATTERN,
    DEFAULT_TOOL_NAME,
    HOOK_EVENT_NAME,
    LABELLED_RULE_WORDING_COMMAND_TEMPLATE,
    LABELLED_RULE_WORDING_LINE_TEMPLATE,
    MAXIMUM_ACTION_SUMMARY_CHARACTERS,
    MAXIMUM_PROSE_RULE_NAME_CHARACTERS,
    NO_VERDICT_CONTEXT_TEMPLATE,
    POWERSHELL_BLOCK_TEMPLATE,
    QUESTION_CONTEXT_TEMPLATE,
    RULE_LABEL_DISALLOWED_CHARACTER_PATTERN,
    SENTENCE_END_PATTERN,
    SUMMARY_WORD_SEPARATOR,
    TRUNCATION_MARKER,
    UNEXPLAINED_RULE_LABEL,
    UNEXPLAINED_VERDICT_REASON_PREFIX,
    UNLABELLED_RULE_WORDING_COMMAND,
    UNLABELLED_RULE_WORDING_LINE_TEMPLATE,
    UNNAMED_RULE_LABEL,
    USER_MESSAGE_TEMPLATE,
    VERDICT_CONTEXT_TEMPLATE,
)


@dataclass(frozen=True)
class DenialReason:
    """One parsed PermissionDenied ``reason``.

    Attributes:
        rule_label: The classifier rule label, or None when the text has none.
        has_verdict: False when auto mode reached no verdict on the action.
        prose: The reason text after the label, or the whole text.
    """

    rule_label: str | None
    has_verdict: bool
    prose: str


def _one_display_line(text: str) -> str:
    single_line_text = SUMMARY_WORD_SEPARATOR.join(text.split())
    return "".join(
        each_character
        for each_character in single_line_text
        if not unicodedata.category(each_character).startswith("C")
    )


def _safe_rule_label(text: str) -> str:
    kept_characters = re.sub(RULE_LABEL_DISALLOWED_CHARACTER_PATTERN, "", _one_display_line(text))
    return SUMMARY_WORD_SEPARATOR.join(kept_characters.split())


def parse_denial_reason(reason: str) -> DenialReason:
    """Split a PermissionDenied ``reason`` into its rule label and prose.

    ::

        "[Git Destructive] force push"      -> label "Git Destructive", verdict
        "[Don't Touch] edits a file"        -> label "Dont Touch", verdict
        "Unauthorized Persistence, because" -> label "Unauthorized Persistence", verdict
        "the command cancels runs."         -> no label, verdict
        "Classifier unavailable"            -> no label, no verdict
        "The server-side auto mode classifier
         gave no verdict (timed out)"       -> no label, no verdict
        "Reason: [Git Destructive] force"   -> label "Git Destructive", verdict
        "The server-side auto mode classifier judged this action dangerous
         (it gave no explanation)"          -> label "Unexplained", verdict

    A leading ``Reason:``, and the classifier sentence ``Permission for this
    action was denied by the Claude Code auto mode classifier.`` before it,
    are dropped first. A reason that starts ``The server-side auto mode
    classifier judged this action dangerous`` gets the label ``Unexplained``,
    and the whole text is the prose. A bracketed label counts only at the
    start of the remaining text. A bare label is two or more capitalised words that end at a comma, colon, semicolon,
    period, spaced dash, or the end of the text. A label keeps only ASCII
    letters, digits, spaces, ``-``, ``_`` and ``/``, with whitespace
    collapsed. A label left with none of them is no label, and the whole
    text is the prose. An empty reason has no verdict, and so has a reason
    that starts ``Auto mode could not evaluate this action``, ``Classifier
    unavailable``, ``The server-side auto mode classifier gave no verdict``
    or ``a hook changed this call's input after auto mode reviewed it``.

    Args:
        reason: The ``reason`` text from the hook input.

    Returns:
        The label or None, whether a verdict exists, and the prose.
    """
    stripped_reason = re.sub(CLASSIFIER_REASON_PREFIX_PATTERN, "", reason, count=1).strip()
    if not stripped_reason or stripped_reason.lower().startswith(ALL_NO_VERDICT_REASON_PREFIXES):
        return DenialReason(rule_label=None, has_verdict=False, prose=stripped_reason)
    if stripped_reason.lower().startswith(UNEXPLAINED_VERDICT_REASON_PREFIX):
        return DenialReason(
            rule_label=UNEXPLAINED_RULE_LABEL, has_verdict=True, prose=stripped_reason
        )
    for each_label_pattern in (BRACKETED_LABEL_PATTERN, BARE_LABEL_PATTERN):
        label_match = re.match(each_label_pattern, stripped_reason, re.DOTALL)
        safe_label = _safe_rule_label(label_match.group("label")) if label_match else ""
        if safe_label:
            return DenialReason(
                rule_label=safe_label,
                has_verdict=True,
                prose=label_match.group("prose").strip(),
            )
    return DenialReason(rule_label=None, has_verdict=True, prose=stripped_reason)


def _prose_rule_name(prose: str) -> str:
    first_sentence = re.split(SENTENCE_END_PATTERN, prose, maxsplit=1)[0]
    cleaned_name = _safe_rule_label(first_sentence)
    if len(cleaned_name) <= MAXIMUM_PROSE_RULE_NAME_CHARACTERS:
        return cleaned_name or UNNAMED_RULE_LABEL
    kept_length = MAXIMUM_PROSE_RULE_NAME_CHARACTERS - len(TRUNCATION_MARKER)
    return cleaned_name[:kept_length] + TRUNCATION_MARKER


def _rule_name_for(denial: DenialReason) -> str:
    if denial.rule_label:
        return denial.rule_label
    if denial.has_verdict:
        return _prose_rule_name(denial.prose)
    return UNNAMED_RULE_LABEL


def _summary_source_text(tool_input: object) -> str:
    if not isinstance(tool_input, dict):
        return json.dumps(tool_input, sort_keys=True)
    for each_key in ALL_COMMAND_INPUT_KEYS:
        if isinstance(tool_input.get(each_key), str):
            return tool_input[each_key]
    return json.dumps(tool_input, sort_keys=True)


def action_summary_from(tool_input: object) -> str:
    """Return one short line that names the denied action.

    Args:
        tool_input: The denied call's ``tool_input``.

    Returns:
        The command, URL or path when the input has one, else the compact
        JSON input, cut to the summary length limit.
    """
    single_line_text = _one_display_line(_summary_source_text(tool_input))
    if len(single_line_text) <= MAXIMUM_ACTION_SUMMARY_CHARACTERS:
        return single_line_text
    kept_length = MAXIMUM_ACTION_SUMMARY_CHARACTERS - len(TRUNCATION_MARKER)
    return single_line_text[:kept_length] + TRUNCATION_MARKER


def _powershell_literal_text(text: str) -> str:
    for each_quote_character in ALL_POWERSHELL_SINGLE_QUOTE_CHARACTERS:
        text = text.replace(each_quote_character, each_quote_character + each_quote_character)
    return text


def powershell_block_for(allow_entry: str) -> str:
    """Return the PowerShell 7 block that adds one allow entry.

    PowerShell ends a single-quoted literal at ``'`` and at the curly quotes
    U+2018 to U+201B, so each of them is doubled.

    Args:
        allow_entry: The ``autoMode.allow`` entry text.

    Returns:
        The block, with the entry in a single-quoted PowerShell literal.
    """
    escaped_entry = _powershell_literal_text(allow_entry)
    return POWERSHELL_BLOCK_TEMPLATE.replace("{escaped_entry}", escaped_entry)


def rule_wording_command_for(rule_label: str | None) -> str:
    """Return the command that prints the classifier rule wording.

    ::

        "Git Destructive" -> claude auto-mode defaults --label 'Git Destructive'
        None              -> claude auto-mode defaults

    Args:
        rule_label: The parsed rule label, or None for a prose-named reason.

    Returns:
        The command, with the label in a single-quoted literal whose quotes
        are doubled.
    """
    if rule_label is None:
        return UNLABELLED_RULE_WORDING_COMMAND
    return LABELLED_RULE_WORDING_COMMAND_TEMPLATE.format(
        escaped_label=_powershell_literal_text(rule_label)
    )


def _rule_wording_line_for(rule_label: str | None) -> str:
    named_rule_label = None if rule_label == UNEXPLAINED_RULE_LABEL else rule_label
    line_template = (
        UNLABELLED_RULE_WORDING_LINE_TEMPLATE
        if named_rule_label is None
        else LABELLED_RULE_WORDING_LINE_TEMPLATE
    )
    return line_template.format(command=rule_wording_command_for(named_rule_label))


def _verdict_context_text(
    tool_name: str, denial_reason: str, action_summary: str, parsed_denial: DenialReason
) -> str:
    rule_label = _rule_name_for(parsed_denial)
    allow_entry = ALLOW_ENTRY_TEMPLATE.format(
        rule_label=rule_label,
        tool_name=tool_name,
        action_summary=action_summary,
    )
    return VERDICT_CONTEXT_TEMPLATE.format(
        tool_name=tool_name,
        rule_label=rule_label,
        denial_reason=denial_reason,
        action_summary=action_summary,
        powershell_block=powershell_block_for(allow_entry),
        rule_wording_line=_rule_wording_line_for(parsed_denial.rule_label),
    )


def build_hook_output(all_denial_fields: dict[str, object]) -> dict[str, object]:
    """Return the PermissionDenied hook output for one denial payload.

    Args:
        all_denial_fields: The hook input JSON.

    Returns:
        A ``hookSpecificOutput`` with ``additionalContext`` for the agent and
        a top-level ``systemMessage`` for the user. A ``reason`` that is not
        text has no verdict, and the reason is shown on one line with
        control characters removed.
    """
    tool_name = str(all_denial_fields.get("tool_name") or DEFAULT_TOOL_NAME)
    raw_reason = all_denial_fields.get("reason")
    denial_reason = _one_display_line(raw_reason) if isinstance(raw_reason, str) else ""
    action_summary = action_summary_from(all_denial_fields.get("tool_input"))
    parsed_denial = parse_denial_reason(denial_reason)
    rule_label = _rule_name_for(parsed_denial)
    if parsed_denial.has_verdict:
        context_text = _verdict_context_text(
            tool_name, denial_reason, action_summary, parsed_denial
        )
    else:
        context_text = NO_VERDICT_CONTEXT_TEMPLATE.format(
            tool_name=tool_name,
            denial_reason=denial_reason,
            action_summary=action_summary,
        )
    return {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "additionalContext": context_text,
        },
        "systemMessage": USER_MESSAGE_TEMPLATE.format(tool_name=tool_name, rule_label=rule_label),
    }


def _refused_step_from(
    all_denial_fields: dict[str, object],
) -> auto_mode_refusal_ledger.RefusedStep | None:
    session_id = all_denial_fields.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    raw_transcript_path = all_denial_fields.get("transcript_path")
    raw_working_folder = all_denial_fields.get("cwd")
    raw_reason = all_denial_fields.get("reason")
    denial_reason = _one_display_line(raw_reason) if isinstance(raw_reason, str) else ""
    tool_input = all_denial_fields.get("tool_input")
    return auto_mode_refusal_ledger.RefusedStep(
        session_id=session_id,
        transcript_path=Path(raw_transcript_path) if isinstance(raw_transcript_path, str) else None,
        tool_name=str(all_denial_fields.get("tool_name") or DEFAULT_TOOL_NAME),
        tool_input=tool_input,
        working_folder=raw_working_folder if isinstance(raw_working_folder, str) else None,
        rule_label=parse_denial_reason(denial_reason).rule_label,
        reason=denial_reason,
        action_summary=action_summary_from(tool_input),
    )


def _question_context_for(all_denial_fields: dict[str, object]) -> str | None:
    playbook_path = auto_mode_refusal_ledger.playbook_path_from_environment()
    if playbook_path is None:
        return None
    repository_root = auto_mode_refusal_ledger.rule_repository_root(playbook_path)
    refused_step = _refused_step_from(all_denial_fields)
    if repository_root is None or refused_step is None:
        return None
    question = auto_mode_refusal_ledger.record_refusal(refused_step, repository_root)
    if question is None:
        return None
    return QUESTION_CONTEXT_TEMPLATE.format(question=question, playbook_path=playbook_path)


def hook_output_with_ledger(all_denial_fields: dict[str, object]) -> dict[str, object]:
    """Return the hook output, with the ledger kept when the flow is on.

    ::

        flow off or playbook missing      -> build_hook_output, byte for byte
        playbook with no repository above -> build_hook_output
        flow on, question returned        -> same, plus the AUTO MODE QUESTION block
        any ledger or transcript error    -> build_hook_output

    Args:
        all_denial_fields: The hook input JSON.

    Returns:
        The PermissionDenied hook output.
    """
    hook_output = build_hook_output(all_denial_fields)
    try:
        question_context = _question_context_for(all_denial_fields)
    except Exception:
        return hook_output
    if question_context is None:
        return hook_output
    hook_specific_output = dict(hook_output["hookSpecificOutput"])
    hook_specific_output["additionalContext"] = (
        str(hook_specific_output["additionalContext"]) + question_context
    )
    return {**hook_output, "hookSpecificOutput": hook_specific_output}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    sys.stdout.write(json.dumps(hook_output_with_ledger(payload)))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
