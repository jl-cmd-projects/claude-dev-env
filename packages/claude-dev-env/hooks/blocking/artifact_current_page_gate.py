#!/usr/bin/env python3
"""PreToolUse hook that keeps a published page at one link with each item drawn once.

A page a person reviews more than once goes wrong in two ways. An agent adds a
section on each round, so one screen is drawn in three places. Or a publish
with no link opens a second copy. This gate reads the page as the publish
would send it and refuses both::

    Artifact {"file_path": "page.html"}                      first publish, each item once  -> allowed
    Artifact {"file_path": "page.html"}                      the page has a recorded link   -> denied, names the link
    Artifact {"file_path": "page.html", "url": "<link>"}     one image drawn three times    -> denied, names the image
    Artifact {"file_path": "page.html", "url": "<link>"}     each item once                 -> allowed, with a note
    Artifact {"action": "read", ...}                         -> allowed

An item is an image larger than an icon, counted by the file its
``src`` names in the rendered page, or an element with a ``data-item``
key. The link record is a ``<meta name="artifact-link">`` tag in the
page, or the record file that ``session/artifact_link_record.py``
writes beside the page.

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

from blocking.artifact_dark_mode_gate import published_page_path, wrap_in_publish_skeleton
from hooks_constants.artifact_current_page_gate_constants import (
    ARTIFACT_EDITS_INPUT_KEY,
    ARTIFACT_LINK_PATTERN,
    ARTIFACT_URL_INPUT_KEY,
    EDIT_NEW_TEXT_KEY,
    EDIT_OLD_TEXT_KEY,
    FULL_RULE_POINTER_TEMPLATE,
    LINK_META_NAME,
    LINK_META_SOURCE,
    LINK_RECORD_SUFFIX,
    LINK_RECORD_TITLE_KEY,
    LINK_RECORD_URL_KEY,
    META_CONTENT_ATTRIBUTE,
    META_NAME_ATTRIBUTE,
    META_TAG_PATTERN,
    PAGE_TITLE_PATTERN,
    REPEAT_ITEM_KEY,
    REPEAT_RENDERER_MISSING_HEADER,
    REPEAT_RENDERER_SCRIPT_PATH,
    REPEAT_TIMES_KEY,
    REPEATED_ITEM_HEADER,
    REPEATED_ITEM_LINE_TEMPLATE,
    REPEATED_ITEM_RETRY_INSTRUCTION,
    REPUBLISH_NOTE,
    LINK_SOURCE_JOINER,
    SECOND_LINK_REASON_TEMPLATE,
    TAG_ATTRIBUTE_PATTERN,
)
from hooks_constants.artifact_dark_mode_gate_constants import (
    ALLOW_EXIT_CODE,
    ARTIFACT_TOOL_NAME,
    BLOCK_EXIT_CODE,
    GATE_EVENT_NAME,
    RENDERER_MISSING_EXIT_CODE,
    RENDERER_TIMEOUT_SECONDS,
)
from hooks_constants.artifact_template_pointer_constants import ARTIFACT_TEMPLATE_PATH
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.spawn_readiness_hook_constants import (
    ADDITIONAL_CONTEXT_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)
from session.artifact_template_pointer import installed_template_path


def page_source_after_edits(page_source: str, all_edits: object) -> str:
    """Return the page as the publish sends it, with the call's ``edits`` applied.

    The Artifact tool applies the edits in order, all or none. Each ``old_str``
    must occur exactly once in the page as it stands. An edit that can add a
    section must be checked too, so the gate applies the same edits first::

        [{"old_str": "old", "new_str": "new"}] on "<p>old</p>"        -> "<p>new</p>"
        one edit whose old_str is missing or occurs twice              -> the page unchanged
        no edits, or an edit that is not an old_str/new_str pair       -> the page unchanged

    A call with a missed edit publishes nothing, so the unchanged page is the
    one the gate reads.

    Args:
        page_source: The HTML in the page file.
        all_edits: The ``edits`` value of the publish call, or None.

    Returns:
        The page source with every edit applied, or the page source unchanged.
    """
    if not isinstance(all_edits, list):
        return page_source
    edited_source = page_source
    for each_edit in all_edits:
        if not isinstance(each_edit, dict):
            return page_source
        old_text = each_edit.get(EDIT_OLD_TEXT_KEY)
        new_text = each_edit.get(EDIT_NEW_TEXT_KEY)
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            return page_source
        if edited_source.count(old_text) != 1:
            return page_source
        edited_source = edited_source.replace(old_text, new_text)
    return edited_source


def page_title(page_source: str) -> str:
    """Return the text of the page's ``<title>``, or an empty string.

    >>> page_title("<title> Sample Run </title><p>x</p>")
    'Sample Run'

    Args:
        page_source: The HTML of the page.
    """
    title_match = PAGE_TITLE_PATTERN.search(page_source)
    return title_match.group(1).strip() if title_match else ""


def link_record_path(page_path: Path) -> Path:
    """Return the record file that holds the link of the page at ``page_path``.

    >>> link_record_path(Path("/work/first-look.html")).name
    'first-look.html.artifact-link.json'

    Args:
        page_path: The local page file.
    """
    return page_path.with_name(page_path.name + LINK_RECORD_SUFFIX)


def _link_record(record_path: Path) -> dict[str, str]:
    try:
        loaded_record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded_record, dict):
        return {}
    return {
        each_key: each_value
        for each_key, each_value in loaded_record.items()
        if isinstance(each_key, str) and isinstance(each_value, str)
    }


def _meta_page_link(page_source: str) -> str:
    for each_meta_tag in META_TAG_PATTERN.findall(page_source):
        all_attributes: dict[str, str] = {}
        for each_name, each_double_quoted, each_single_quoted in TAG_ATTRIBUTE_PATTERN.findall(
            each_meta_tag
        ):
            all_attributes.setdefault(
                each_name.lower(), (each_double_quoted or each_single_quoted).strip()
            )
        meta_link = all_attributes.get(META_CONTENT_ATTRIBUTE, "")
        if all_attributes.get(
            META_NAME_ATTRIBUTE, ""
        ).lower() == LINK_META_NAME and ARTIFACT_LINK_PATTERN.fullmatch(meta_link):
            return meta_link
    return ""


def _record_link(record_path: Path) -> str:
    recorded_link = _link_record(record_path).get(LINK_RECORD_URL_KEY, "")
    return recorded_link if ARTIFACT_LINK_PATTERN.fullmatch(recorded_link) else ""


def _renamed_page_record(page_path: Path, title: str) -> Path | None:
    if not title:
        return None
    all_record_paths = sorted(page_path.parent.glob("*" + LINK_RECORD_SUFFIX))
    page_path_by_record = {
        each_record_path: page_path.parent / each_record_path.name.removesuffix(LINK_RECORD_SUFFIX)
        for each_record_path in all_record_paths
    }
    links_of_other_present_pages = {
        _record_link(each_record_path)
        for each_record_path, each_page_path in page_path_by_record.items()
        if each_page_path.exists() and each_page_path != page_path
    }
    for each_record_path, each_page_path in page_path_by_record.items():
        if each_page_path.exists():
            continue
        each_link = _record_link(each_record_path)
        is_same_title = _link_record(each_record_path).get(LINK_RECORD_TITLE_KEY) == title
        if is_same_title and each_link and each_link not in links_of_other_present_pages:
            return each_record_path
    return None


def _page_link_and_source(page_path: Path, page_source: str) -> tuple[str, str]:
    all_links_with_sources: list[tuple[str, str]] = []
    meta_link = _meta_page_link(page_source)
    if meta_link:
        all_links_with_sources.append((meta_link, LINK_META_SOURCE))
    own_record_path = link_record_path(page_path)
    own_link = _record_link(own_record_path)
    if own_link:
        all_links_with_sources.append((own_link, str(own_record_path)))
    renamed_record_path = _renamed_page_record(page_path, page_title(page_source))
    if renamed_record_path is not None:
        all_links_with_sources.append(
            (_record_link(renamed_record_path), str(renamed_record_path))
        )
    if not all_links_with_sources:
        return "", ""
    first_link = all_links_with_sources[0][0]
    return first_link, LINK_SOURCE_JOINER.join(
        each_source for _, each_source in all_links_with_sources
    )


def recorded_page_link(page_path: Path, page_source: str) -> str:
    """Return the link this page was published at before, or an empty string.

    The gate looks in three places, in this order::

        <meta name="artifact-link" content="<link>"> in the page       -> that link
        first-look.html.artifact-link.json beside first-look.html      -> its url
        a record in the same folder with this title, page file gone    -> its url

    Each place counts only when it holds an artifact link, and the meta tag
    counts in either attribute order. The third place catches a page renamed
    in its folder. A record whose page file is still there belongs to a
    separate page, even when the two titles match, so it is skipped. So is a
    record whose link another page in the folder still holds.

    Args:
        page_path: The local page file.
        page_source: The HTML the publish sends.

    Returns:
        The recorded link, or an empty string when the page has none.
    """
    return _page_link_and_source(page_path, page_source)[0]


def _run_renderer(wrapped_page_path: Path) -> subprocess.CompletedProcess[str] | str:
    try:
        return subprocess.run(
            ["node", str(REPEAT_RENDERER_SCRIPT_PATH), str(wrapped_page_path)],
            capture_output=True,
            text=True,
            timeout=RENDERER_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return "node is not installed; install Node.js, then run: npm install -g playwright && npx playwright install chromium"
    except subprocess.TimeoutExpired:
        return f"the render took longer than {RENDERER_TIMEOUT_SECONDS} seconds"


def repeated_items(page_source: str) -> tuple[list[dict[str, object]] | None, str]:
    """Render the wrapped page and return each item it draws more than once.

    Args:
        page_source: The HTML the publish sends.

    Returns:
        The repeats (empty when each item is drawn once) and an empty message,
        or None and the reason the renderer could not run.
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
        all_repeats = json.loads(completed_render.stdout)
    except ValueError:
        all_repeats = None
    if not isinstance(all_repeats, list):
        return None, completed_render.stderr.strip() or "the renderer printed no result"
    return all_repeats, ""


def full_rule_pointer() -> str:
    """Return the sentence that names where the installed rule text sits.

    Returns:
        One sentence with the path of the artifact page README on this host.
    """
    return FULL_RULE_POINTER_TEMPLATE.format(
        path_of_page_readme=installed_template_path(ARTIFACT_TEMPLATE_PATH)
    )


def format_repeat_reason(all_repeats: list[dict[str, object]]) -> str:
    """Return the deny message that names each repeated item and its count.

    Args:
        all_repeats: The repeats the renderer reported, most repeated first.

    Returns:
        The message the session reads when the publish is denied.
    """
    all_lines = [REPEATED_ITEM_HEADER]
    all_lines.extend(
        REPEATED_ITEM_LINE_TEMPLATE.format(
            item=each_repeat.get(REPEAT_ITEM_KEY), times=each_repeat.get(REPEAT_TIMES_KEY)
        )
        for each_repeat in all_repeats
    )
    return "".join(all_lines) + REPEATED_ITEM_RETRY_INSTRUCTION + full_rule_pointer()


def _block(block_reason: str, page_path: Path) -> int:
    log_hook_block(
        Path(__file__).name,
        GATE_EVENT_NAME,
        block_reason,
        tool_name=ARTIFACT_TOOL_NAME,
        offending_input_preview=str(page_path),
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


def _republish_note_output() -> dict[str, dict[str, str]]:
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: GATE_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: REPUBLISH_NOTE + full_rule_pointer(),
        }
    }


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    page_path = published_page_path(hook_input.get(TOOL_NAME_KEY), tool_input)
    if page_path is None or not page_path.is_file() or not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    page_source = page_source_after_edits(
        page_path.read_text(encoding="utf-8", errors="replace"),
        tool_input.get(ARTIFACT_EDITS_INPUT_KEY),
    )
    has_link_in_call = bool(tool_input.get(ARTIFACT_URL_INPUT_KEY))
    recorded_link, link_source = _page_link_and_source(page_path, page_source)
    if recorded_link and not has_link_in_call:
        return _block(
            SECOND_LINK_REASON_TEMPLATE.format(link=recorded_link, link_source=link_source),
            page_path,
        )
    all_repeats, renderer_problem = repeated_items(page_source)
    if all_repeats is None:
        return _block(REPEAT_RENDERER_MISSING_HEADER + renderer_problem, page_path)
    if all_repeats:
        return _block(format_repeat_reason(all_repeats), page_path)
    if has_link_in_call:
        sys.stdout.write(json.dumps(_republish_note_output()))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
