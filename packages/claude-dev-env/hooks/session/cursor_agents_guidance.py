#!/usr/bin/env python3
"""Cursor sessionStart hook that puts the installed agent guidance into every session.

Cursor keeps user rules in its app settings, and it reads ``~/.cursor/rules``
only for a workspace inside the home directory, so no file under ``~/.cursor``
carries global guidance. The installer registers this hook as a native
``sessionStart`` entry in ``~/.cursor/hooks.json`` with the installed
``AGENTS.md`` path as its one argument. The hook prints that file as Cursor's
``additional_context``, which Cursor adds to the session's context::

    python3 cursor_agents_guidance.py ~/.agents/AGENTS.md
    -> {"additional_context": "# Agent guidance ..."}

A missing or unreadable file prints ``{}`` so the session starts without it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.cursor_agents_guidance_constants import (
    CURSOR_CONTEXT_KEY,
    EMPTY_OUTPUT,
    GUIDANCE_PATH_ARGUMENT_INDEX,
    UTF8_ENCODING,
)


def guidance_output(all_arguments: list[str]) -> str:
    """Return the SessionStart output for the guidance file named in the arguments."""
    if len(all_arguments) <= GUIDANCE_PATH_ARGUMENT_INDEX:
        return EMPTY_OUTPUT
    try:
        guidance_text = Path(all_arguments[GUIDANCE_PATH_ARGUMENT_INDEX]).read_text(encoding=UTF8_ENCODING)
    except OSError:
        return EMPTY_OUTPUT
    if not guidance_text.strip():
        return EMPTY_OUTPUT
    return json.dumps({CURSOR_CONTEXT_KEY: guidance_text})


def main() -> None:
    sys.stdin.read()
    sys.stdout.write(guidance_output(sys.argv))


if __name__ == "__main__":
    main()
