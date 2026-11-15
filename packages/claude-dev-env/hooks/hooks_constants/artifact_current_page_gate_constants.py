"""Names, patterns and messages for the artifact current page gate and its link record."""

from __future__ import annotations

import re

from hooks_constants.artifact_dark_mode_gate_constants import BLOCKING_HOOKS_DIRECTORY

__all__ = [
    "ARTIFACT_EDITS_INPUT_KEY",
    "ARTIFACT_LINK_PATTERN",
    "ARTIFACT_URL_INPUT_KEY",
    "EDIT_NEW_TEXT_KEY",
    "EDIT_OLD_TEXT_KEY",
    "FULL_RULE_POINTER_TEMPLATE",
    "LINK_META_NAME",
    "LINK_META_SOURCE",
    "LINK_RECORD_SUFFIX",
    "LINK_RECORD_TITLE_KEY",
    "LINK_RECORD_URL_KEY",
    "LINK_SOURCE_JOINER",
    "LINK_SOURCE_WITH_OTHER_LINK_TEMPLATE",
    "META_CONTENT_ATTRIBUTE",
    "META_NAME_ATTRIBUTE",
    "META_TAG_PATTERN",
    "PAGE_TITLE_PATTERN",
    "REPEATED_ITEM_HEADER",
    "REPEATED_ITEM_LINE_TEMPLATE",
    "REPEATED_ITEM_RETRY_INSTRUCTION",
    "REPEAT_ITEM_KEY",
    "REPEAT_RENDERER_MISSING_HEADER",
    "REPEAT_RENDERER_SCRIPT_PATH",
    "REPEAT_TIMES_KEY",
    "REPUBLISH_NOTE",
    "SECOND_LINK_REASON_TEMPLATE",
    "TAG_ATTRIBUTE_PATTERN",
    "TOOL_RESPONSE_KEY",
]

ARTIFACT_URL_INPUT_KEY = "url"
ARTIFACT_EDITS_INPUT_KEY = "edits"
EDIT_OLD_TEXT_KEY = "old_str"
EDIT_NEW_TEXT_KEY = "new_str"
TOOL_RESPONSE_KEY = "tool_response"
LINK_RECORD_SUFFIX = ".artifact-link.json"
LINK_RECORD_URL_KEY = "url"
LINK_RECORD_TITLE_KEY = "title"
REPEAT_ITEM_KEY = "item"
REPEAT_TIMES_KEY = "times"
ARTIFACT_LINK_PATTERN = re.compile(r"https://claude\.ai/(?:code/)?artifact/[A-Za-z0-9_-]+")
META_TAG_PATTERN = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
TAG_ATTRIBUTE_PATTERN = re.compile(r"""(?<=\s)([^\s=/>"']+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
META_NAME_ATTRIBUTE = "name"
META_CONTENT_ATTRIBUTE = "content"
LINK_META_NAME = "artifact-link"
LINK_META_SOURCE = "the artifact-link meta tag from the page"
LINK_SOURCE_JOINER = " and "
LINK_SOURCE_WITH_OTHER_LINK_TEMPLATE = "{source}, which holds {link}"
PAGE_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
REPEAT_RENDERER_SCRIPT_PATH = BLOCKING_HOOKS_DIRECTORY / "artifact_repeated_item_render.cjs"
REPEATED_ITEM_HEADER = "This page draws the same item more than once, so the reader cannot tell which entry is current.\n"
REPEATED_ITEM_LINE_TEMPLATE = "- {item} is drawn {times} times\n"
REPEATED_ITEM_RETRY_INSTRUCTION = (
    "\nRebuild the page from the current state. Show each item once, and put its status and"
    " every warning that names it on that one entry. Remove each section that repeats an item,"
    " and remove content that a newer result replaced. State at the top what the page shows and"
    " when it was updated. Then publish again to the same link. A small icon that is used many"
    " times needs a width and height of 64 pixels or less."
)
SECOND_LINK_REASON_TEMPLATE = (
    "This page already has a link: {link}\n"
    "A publish with no url opens a second link, and the reader then holds two copies."
    " Publish again with url set to that link. A separate page gets its own file and its own"
    " title. When the user asks for a separate copy, or says the page at that link was deleted,"
    " remove {link_source}, then publish with no url."
)
FULL_RULE_POINTER_TEMPLATE = ' The full rule is under "Republish a page" in {path_of_page_readme}.'
REPEAT_RENDERER_MISSING_HEADER = (
    "The page did not render for its repeated item check before publish: "
)
REPUBLISH_NOTE = (
    "This publish updates a page a person has already seen. Rebuild the page from the current"
    " state: each item once, with its status and warnings on that one entry; content that a"
    " newer result replaced removed; and a line at the top that says what the page shows and"
    " when it was updated."
)
