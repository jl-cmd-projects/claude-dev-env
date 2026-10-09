#!/usr/bin/env python3
"""PreToolUse hook that stops an artifact page from publishing when dark mode hides its text.

The artifact service wraps every published page in a skeleton whose style pins
``body`` to a light background and dark text. A page that flips its theme
tokens on ``html`` alone keeps that light body in dark mode, and its light
dark-mode text lands on it. A plain local render has no wrapper, so the page
looks fine there and fails once published.

This gate renders the page inside that same wrapper in headless Chromium,
once under ``prefers-color-scheme: dark`` and once with ``data-theme="dark"``
on the root element::

    Artifact {"action": "publish", "file_path": "page.html"}  -> rendered
        body stays light, or visible text under 4.5:1      -> denied
        every check holds                                  -> allowed
    Artifact {"action": "read", ...}                       -> allowed
    Artifact {"asset": true, ...} or {"type_url": ...}     -> allowed
    a publish whose file_path is not .html                 -> allowed

A host without Playwright or Chromium is denied with the install command,
because an unrendered page is the case this gate exists to stop.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.artifact_dark_mode_gate_constants import (
    ALL_SKIPPED_PUBLISH_INPUT_KEYS,
    ALLOW_EXIT_CODE,
    ARTIFACT_ACTION_INPUT_KEY,
    ARTIFACT_FILE_PATH_INPUT_KEY,
    ARTIFACT_PUBLISH_ACTION,
    ARTIFACT_TOOL_NAME,
    BLOCK_EXIT_CODE,
    DARK_MODE_FAILURE_HEADER,
    GATE_EVENT_NAME,
    HTML_FILE_SUFFIX,
    PUBLISH_SKELETON_PREFIX,
    RENDERER_MISSING_EXIT_CODE,
    RENDERER_MISSING_HEADER,
    RENDERER_SCRIPT_PATH,
    RENDERER_TIMEOUT_SECONDS,
    RETRY_INSTRUCTION,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.spawn_readiness_hook_constants import TOOL_INPUT_KEY, TOOL_NAME_KEY


def published_page_path(tool_name: object, tool_input: object) -> Path | None:
    """Return the local HTML page a call publishes as an artifact page, or None.

    >>> published_page_path("Artifact", {"file_path": "/tmp/page.html"})
    PosixPath('/tmp/page.html')
    >>> published_page_path("Artifact", {"action": "read", "url": "x"}) is None
    True

    Args:
        tool_name: The tool the session called.
        tool_input: The tool input.

    Returns:
        The page path for a page publish, or None for any other call.
    """
    if tool_name != ARTIFACT_TOOL_NAME or not isinstance(tool_input, dict):
        return None
    if (
        tool_input.get(ARTIFACT_ACTION_INPUT_KEY, ARTIFACT_PUBLISH_ACTION)
        != ARTIFACT_PUBLISH_ACTION
    ):
        return None
    if any(tool_input.get(each_key) for each_key in ALL_SKIPPED_PUBLISH_INPUT_KEYS):
        return None
    file_path = tool_input.get(ARTIFACT_FILE_PATH_INPUT_KEY)
    if not isinstance(file_path, str) or not file_path.lower().endswith(HTML_FILE_SUFFIX):
        return None
    return Path(file_path)


def wrap_in_publish_skeleton(page_source: str) -> str:
    """Return the page as the artifact service serves it, inside its skeleton.

    Args:
        page_source: The HTML the session is about to publish.

    Returns:
        The skeleton head and body opening followed by the page source.
    """
    return PUBLISH_SKELETON_PREFIX + page_source


def _run_renderer(wrapped_page_path: Path) -> subprocess.CompletedProcess[str] | str:
    try:
        return subprocess.run(
            ["node", str(RENDERER_SCRIPT_PATH), str(wrapped_page_path)],
            capture_output=True,
            text=True,
            timeout=RENDERER_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return "node is not installed; install Node.js, then run: npm install -g playwright && npx playwright install chromium"
    except subprocess.TimeoutExpired:
        return f"the render took longer than {RENDERER_TIMEOUT_SECONDS} seconds"


def render_findings(page_source: str) -> tuple[dict[str, list[str]] | None, str]:
    """Render the wrapped page in both dark signals and return what failed.

    Args:
        page_source: The HTML the session is about to publish.

    Returns:
        The findings by dark signal (empty when the page passes) and an empty
        message, or None and the reason the renderer could not run.
    """
    with tempfile.TemporaryDirectory() as scratch_directory:
        wrapped_page_path = Path(scratch_directory) / "wrapped_page.html"
        wrapped_page_path.write_text(wrap_in_publish_skeleton(page_source), encoding="utf-8")
        completed_render = _run_renderer(wrapped_page_path)
    if isinstance(completed_render, str):
        return None, completed_render
    if completed_render.returncode == RENDERER_MISSING_EXIT_CODE:
        return None, completed_render.stderr.strip()
    try:
        findings_by_signal = json.loads(completed_render.stdout)
    except json.JSONDecodeError:
        return None, completed_render.stderr.strip() or "the renderer printed no result"
    return findings_by_signal, ""


def format_block_reason(findings_by_signal: dict[str, list[str]]) -> str:
    """Return the deny message that lists each failed check under its dark signal.

    Args:
        findings_by_signal: Findings keyed by the dark signal that produced them.

    Returns:
        The message the session reads when the publish is denied.
    """
    all_lines = [DARK_MODE_FAILURE_HEADER]
    for each_signal, each_signal_findings in findings_by_signal.items():
        all_lines.append(f"Under {each_signal}:\n")
        all_lines.extend(f"- {each_finding}\n" for each_finding in each_signal_findings)
    return "".join(all_lines) + RETRY_INSTRUCTION


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    page_path = published_page_path(hook_input.get(TOOL_NAME_KEY), hook_input.get(TOOL_INPUT_KEY))
    if page_path is None or not page_path.is_file():
        return ALLOW_EXIT_CODE
    findings_by_signal, renderer_problem = render_findings(page_path.read_text(encoding="utf-8"))
    if findings_by_signal is None:
        block_reason = RENDERER_MISSING_HEADER + renderer_problem
    elif findings_by_signal:
        block_reason = format_block_reason(findings_by_signal)
    else:
        return ALLOW_EXIT_CODE
    log_hook_block(
        Path(__file__).name,
        GATE_EVENT_NAME,
        block_reason,
        tool_name=ARTIFACT_TOOL_NAME,
        offending_input_preview=str(page_path),
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
