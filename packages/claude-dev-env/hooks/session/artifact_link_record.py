#!/usr/bin/env python3
"""PostToolUse hook that records the link of a published page beside the page file.

An agent that republishes a page must pass the page's link, or the publish
opens a second copy. An agent that lost its context has no other place to
find the link. This hook writes it down after each page publish::

    Artifact {"file_path": "/work/first-look.html"}  -> result names https://claude.ai/artifact/abc
        writes /work/first-look.html.artifact-link.json  {"url": "...", "title": "..."}
    Artifact {"file_path": "...", "url": "<link>"}   -> records <link>
    Artifact {"action": "read", ...}                 -> no record

``blocking/artifact_current_page_gate.py`` reads the record on the next
publish. The hook never blocks and prints nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from blocking.artifact_current_page_gate import link_record_path, page_title
from blocking.artifact_dark_mode_gate import published_page_path
from hooks_constants.artifact_current_page_gate_constants import (
    ARTIFACT_LINK_PATTERN,
    ARTIFACT_URL_INPUT_KEY,
    LINK_RECORD_TITLE_KEY,
    LINK_RECORD_URL_KEY,
    TOOL_RESPONSE_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.spawn_readiness_hook_constants import TOOL_INPUT_KEY, TOOL_NAME_KEY


def published_link(all_tool_input: dict[str, object], tool_response: object) -> str:
    """Return the link a page publish went to, or an empty string.

    A publish that passes ``url`` went to that link. A first publish names its
    new link in the tool result, under ``url`` or in its text::

        {"url": "https://claude.ai/artifact/abc"}, <any result>    -> https://claude.ai/artifact/abc
        {}, {"url": "https://claude.ai/artifact/xyz", ...}         -> https://claude.ai/artifact/xyz
        {}, "Published to https://claude.ai/artifact/xyz"          -> https://claude.ai/artifact/xyz
        {}, "Copied from <link a> to <link b>"                     -> ""
        {}, "The publish was refused"                              -> ""

    Result text that names two different links does not say which one is the
    page, so it gives no link. A call ``url`` that is no artifact link is
    skipped.

    Args:
        all_tool_input: The input of the publish call.
        tool_response: The tool result, as text or as a parsed object.

    Returns:
        The link, or an empty string when neither place names one.
    """
    link_in_call = all_tool_input.get(ARTIFACT_URL_INPUT_KEY)
    if isinstance(link_in_call, str) and ARTIFACT_LINK_PATTERN.fullmatch(link_in_call):
        return link_in_call
    if isinstance(tool_response, dict):
        link_in_result = tool_response.get(ARTIFACT_URL_INPUT_KEY)
        if isinstance(link_in_result, str) and ARTIFACT_LINK_PATTERN.fullmatch(link_in_result):
            return link_in_result
    response_text = (
        tool_response if isinstance(tool_response, str) else json.dumps(tool_response, default=str)
    )
    all_links_in_text = set(ARTIFACT_LINK_PATTERN.findall(response_text))
    return all_links_in_text.pop() if len(all_links_in_text) == 1 else ""


def record_page_link(page_path: Path, link: str) -> None:
    """Write the link record beside the page, and skip a page file that cannot be read.

    Args:
        page_path: The local page file that was published.
        link: The link the page was published at.
    """
    try:
        title = page_title(page_path.read_text(encoding="utf-8", errors="replace"))
        link_record_path(page_path).write_text(
            json.dumps({LINK_RECORD_URL_KEY: link, LINK_RECORD_TITLE_KEY: title}) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return 0
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    page_path = published_page_path(hook_input.get(TOOL_NAME_KEY), tool_input)
    if page_path is None or not page_path.is_file() or not isinstance(tool_input, dict):
        return 0
    link = published_link(tool_input, hook_input.get(TOOL_RESPONSE_KEY))
    if link:
        record_page_link(page_path, link)
    return 0


if __name__ == "__main__":
    sys.exit(main())
