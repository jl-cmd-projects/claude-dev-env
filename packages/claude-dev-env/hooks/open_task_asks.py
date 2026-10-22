"""Tell a prompt that asks for work from one that does not.

The open tasks Stop gate, the session title gate, and the ask tracking nudge
read a prompt through ``is_ask``. A question-only prompt, an acknowledgement
such as ``thanks!``, an empty prompt, a prompt of only ``<system-reminder>``
blocks, and an envelope such as ``<agent-message>`` or ``<task-notification>``
ask for no work.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from hooks_constants.open_tasks_stop_gate_constants import (
    ACKNOWLEDGEMENT_PATTERN,
    ALL_ASK_ONLY_ENVELOPE_MARKERS,
    CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE,
    CLAUDE_HOME_DIRECTORY_NAME,
    INTERROGATIVE_START_PATTERN,
    POLITE_REQUEST_START_PATTERN,
    QUESTION_END_PATTERN,
    SENTENCE_SPLIT_PATTERN,
    SYSTEM_REMINDER_BLOCK_PATTERN,
    YES_OR_NO_END_PATTERN,
)
from hooks_constants.spawn_readiness_hook_constants import ALL_HARNESS_ENVELOPE_MARKERS


def claude_home() -> Path:
    """Return the Claude home directory, honoring ``CLAUDE_CONFIG_DIR``."""
    configured_directory = os.environ.get(CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE)
    if configured_directory:
        return Path(configured_directory)
    return Path.home() / CLAUDE_HOME_DIRECTORY_NAME


def is_question_only(prompt_text: str) -> bool:
    """Return True when the prompt asks a question and asks for no work.

    ::

        "did the export fail?"                      -> True
        "are you monitoring these? yes or no"       -> True
        "can you check the release dates in neon?"  -> False
        "Export the APKs and submit them"           -> False
    """
    all_sentences = [
        each_part.strip()
        for each_part in re.split(SENTENCE_SPLIT_PATTERN, prompt_text.strip())
        if each_part.strip()
    ]
    if not all_sentences or re.search(POLITE_REQUEST_START_PATTERN, prompt_text, re.IGNORECASE):
        return False
    if all(re.search(QUESTION_END_PATTERN, each_sentence) for each_sentence in all_sentences):
        return True
    return bool(
        re.search(YES_OR_NO_END_PATTERN, all_sentences[-1], re.IGNORECASE)
        and re.search(INTERROGATIVE_START_PATTERN, all_sentences[0], re.IGNORECASE)
    )


def prompt_without_reminders(prompt_text: str) -> str:
    """Return the prompt with every ``<system-reminder>`` block removed, stripped."""
    return re.sub(SYSTEM_REMINDER_BLOCK_PATTERN, "", prompt_text, flags=re.DOTALL).strip()


def is_ask(prompt_text: str) -> bool:
    """Return True when the prompt asks for work the gate should hold the turn for.

    ::

        '<agent-message from="a1">Report</agent-message>'    -> False
        "<system-reminder>Tool loaded.</system-reminder>"     -> False
        "<system-reminder>...</system-reminder> Export it"    -> True
    """
    stripped_text = prompt_without_reminders(prompt_text)
    all_envelope_markers = (*ALL_HARNESS_ENVELOPE_MARKERS, *ALL_ASK_ONLY_ENVELOPE_MARKERS)
    if not stripped_text or stripped_text.startswith(all_envelope_markers):
        return False
    if re.fullmatch(ACKNOWLEDGEMENT_PATTERN, stripped_text, re.IGNORECASE):
        return False
    return not is_question_only(stripped_text)
