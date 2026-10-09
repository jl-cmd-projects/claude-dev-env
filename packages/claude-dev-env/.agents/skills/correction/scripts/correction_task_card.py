"""Build the Suggested task card that hands one correction to a fix session.

The agent pipes a JSON object on standard input, and the script prints the
three fields `spawn_task` takes::

    python correction_task_card.py <<'CARD'
    {"title": "Add a lint for bare except in hooks",
     "tldr": "Agents keep writing bare except blocks in hooks.",
     "brief": "Correction: stop writing bare except ...",
     "files": ["packages/claude-dev-env/hooks/blocking/example.py"]}
    CARD
    {"title": "Add a lint ...", "tldr": "Agents keep ...", "prompt": "Land this correction ..."}

The prompt carries the brief, the files, and the fix playbook steps from step 2
on, so a fresh session needs nothing else. `--prompt-only` prints the prompt
alone, for the handoff brief a session without `spawn_task` shows instead.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from correction_task_card_constants.config.constants import (
    ABSOLUTE_PATH_PATTERN,
    ALL_CARD_KEYS,
    BRIEF_KEY,
    FAILURE_EXIT_CODE,
    FILE_LINE_TEMPLATE,
    FILES_KEY,
    FIX_PLAYBOOK_DIRECTORY_NAME,
    FIX_PLAYBOOK_FILE_NAME,
    FIX_PLAYBOOK_FIRST_HANDED_OFF_STEP,
    INVALID_INPUT_MESSAGE_TEMPLATE,
    LINE_SEPARATOR,
    MARKDOWN_LINK_PATTERN,
    MAXIMUM_TITLE_LENGTH,
    NO_FILES_LINE,
    PROMPT_TEMPLATE,
    REASON_ABSOLUTE_FILE_TEMPLATE,
    REASON_EMPTY_FIELD_TEMPLATE,
    REASON_FILES_NOT_A_LIST,
    REASON_MULTI_LINE_FIELD_TEMPLATE,
    REASON_NOT_AN_OBJECT,
    REASON_TITLE_TOO_LONG_TEMPLATE,
    SUCCESS_EXIT_CODE,
    TITLE_KEY,
    TLDR_KEY,
    UTF8_ENCODING,
)


class CardInputRunFatal(ValueError):
    """Stop the run when the piped card input breaks a field rule."""


def _fix_playbook_path() -> Path:
    skill_directory = Path(__file__).resolve().parent.parent
    return skill_directory / FIX_PLAYBOOK_DIRECTORY_NAME / FIX_PLAYBOOK_FILE_NAME


def handed_off_playbook_steps(playbook_text: str) -> str:
    """Return the fix playbook from step 2 on, with each link reduced to its text.

    Args:
        playbook_text: the whole fix playbook.

    Returns:
        Step 2 through the reply line, readable without the skill's folder.
    """
    first_step_index = (
        playbook_text.index(LINE_SEPARATOR + FIX_PLAYBOOK_FIRST_HANDED_OFF_STEP) + 1
    )
    return re.sub(
        MARKDOWN_LINK_PATTERN, r"\1", playbook_text[first_step_index:]
    ).strip()


def _required_text(all_card_fields: dict[str, object], field: str) -> str:
    raw_text = all_card_fields.get(field, "")
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    if not text:
        raise CardInputRunFatal(REASON_EMPTY_FIELD_TEMPLATE.format(field=field))
    return text


def _one_line_text(all_card_fields: dict[str, object], field: str) -> str:
    text = _required_text(all_card_fields, field)
    if LINE_SEPARATOR in text:
        raise CardInputRunFatal(REASON_MULTI_LINE_FIELD_TEMPLATE.format(field=field))
    return text


def _card_title(all_card_fields: dict[str, object]) -> str:
    title = _one_line_text(all_card_fields, TITLE_KEY)
    if len(title) > MAXIMUM_TITLE_LENGTH:
        raise CardInputRunFatal(
            REASON_TITLE_TOO_LONG_TEMPLATE.format(
                length=len(title), limit=MAXIMUM_TITLE_LENGTH
            )
        )
    return title


def _file_lines(all_card_fields: dict[str, object]) -> str:
    all_files = all_card_fields.get(FILES_KEY, [])
    if not isinstance(all_files, list) or not all(
        isinstance(each, str) for each in all_files
    ):
        raise CardInputRunFatal(REASON_FILES_NOT_A_LIST)
    all_named_paths = [each_path.strip() for each_path in all_files if each_path.strip()]
    for each_path in all_named_paths:
        if re.match(ABSOLUTE_PATH_PATTERN, each_path):
            raise CardInputRunFatal(REASON_ABSOLUTE_FILE_TEMPLATE.format(path=each_path))
    all_lines = [FILE_LINE_TEMPLATE.format(path=each_path) for each_path in all_named_paths]
    return LINE_SEPARATOR.join(all_lines) or NO_FILES_LINE


def build_task_card(
    all_card_fields: dict[str, object], playbook_text: str
) -> dict[str, str]:
    """Return the title, tldr, and standalone prompt for `spawn_task`.

    Args:
        all_card_fields: the parsed object with title, tldr, brief, and files.
        playbook_text: the whole fix playbook.

    Returns:
        The three `spawn_task` fields, in the order the tool lists them.

    Raises:
        CardInputRunFatal: a field is empty, spans lines, runs long, or names
            an absolute file path.
    """
    prompt = PROMPT_TEMPLATE.format(
        brief=_required_text(all_card_fields, BRIEF_KEY),
        file_lines=_file_lines(all_card_fields),
        playbook_steps=handed_off_playbook_steps(playbook_text),
    )
    all_card_texts = (
        _card_title(all_card_fields),
        _one_line_text(all_card_fields, TLDR_KEY),
        prompt,
    )
    return dict(zip(ALL_CARD_KEYS, all_card_texts))


def _parsed_card_fields(piped_text: str) -> dict[str, object]:
    try:
        all_card_fields = json.loads(piped_text)
    except json.JSONDecodeError as error:
        raise CardInputRunFatal(REASON_NOT_AN_OBJECT) from error
    if not isinstance(all_card_fields, dict):
        raise CardInputRunFatal(REASON_NOT_AN_OBJECT)
    return all_card_fields


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a correction task card.")
    parser.add_argument("--prompt-only", action="store_true")
    return parser


def main(all_arguments: list[str]) -> int:
    """Read the card input from standard input and print the card or its prompt.

    Args:
        all_arguments: the command-line arguments after the script name.

    Returns:
        The process exit code.
    """
    parsed_arguments = _build_parser().parse_args(all_arguments)
    playbook_text = _fix_playbook_path().read_text(encoding=UTF8_ENCODING)
    try:
        all_card_fields = _parsed_card_fields(
            sys.stdin.buffer.read().decode(UTF8_ENCODING)
        )
        task_card = build_task_card(all_card_fields, playbook_text)
    except CardInputRunFatal as error:
        sys.stderr.write(INVALID_INPUT_MESSAGE_TEMPLATE.format(reason=error))
        return FAILURE_EXIT_CODE
    if parsed_arguments.prompt_only:
        sys.stdout.write(task_card["prompt"])
    else:
        sys.stdout.write(json.dumps(task_card) + LINE_SEPARATOR)
    return SUCCESS_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
