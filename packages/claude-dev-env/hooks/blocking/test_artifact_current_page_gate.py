"""Behavior tests for the artifact current page publish gate."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from blocking.artifact_current_page_gate import (
    format_repeat_reason,
    full_rule_pointer,
    link_record_path,
    page_source_after_edits,
    page_title,
    recorded_page_link,
    repeated_items,
)
from hooks_constants.artifact_current_page_gate_constants import REPUBLISH_NOTE
from hooks_constants.artifact_dark_mode_gate_constants import ALLOW_EXIT_CODE, BLOCK_EXIT_CODE

GATE_SCRIPT_PATH = Path(__file__).resolve().parent / "artifact_current_page_gate.py"
FIXTURES_DIRECTORY = Path(__file__).resolve().parent / "artifact_current_page_fixtures"
PILED_PAGE_PATH = FIXTURES_DIRECTORY / "piled_review_page.html"
REBUILT_PAGE_PATH = FIXTURES_DIRECTORY / "rebuilt_review_page.html"
PAGE_LINK = "https://claude.ai/artifact/SamplePageLink01"
ITEM_IMAGE_STYLE = "<style>img{width:200px;height:300px}</style>"
PAGE_WITH_ONE_SCREEN = (
    "<title>Sample Run</title>" + ITEM_IMAGE_STYLE + '<img src="screens/home.png" alt="Home">'
)
SECOND_DRAW_OF_THE_SCREEN = '<h2>Warnings</h2><img src="screens/home.png" alt="Home again">'


def _renderer_available() -> bool:
    if shutil.which("node") is None:
        return False
    all_repeats, _ = repeated_items("<p>probe</p>")
    return all_repeats is not None


needs_renderer = pytest.mark.skipif(
    not _renderer_available(), reason="node Playwright with Chromium is not installed"
)


def _run_gate(tool_input: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE_SCRIPT_PATH)],
        input=json.dumps({"tool_name": "Artifact", "tool_input": tool_input}),
        capture_output=True,
        text=True,
        check=False,
    )


def _figure_counts_in_data_block(page_path: Path) -> tuple[int, int]:
    data_block = re.search(
        r'<script type="application/json" id="data">(.*?)</script>',
        page_path.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert data_block is not None
    page_data = json.loads(data_block.group(1))
    all_screen_lists = [each_group["screens"] for each_group in page_data.get("groups", [])]
    if isinstance(page_data.get("warnings"), list):
        all_screen_lists += [each_warning["screens"] for each_warning in page_data["warnings"]]
    all_screen_lists += [each_section["screens"] for each_section in page_data.get("sections", [])]
    all_screen_lists.append(page_data.get("pick", {}).get("strips", []))
    all_drawn_names = [
        each_screen[0] for each_screen_list in all_screen_lists for each_screen in each_screen_list
    ]
    return len(all_drawn_names), len(Counter(all_drawn_names))


def test_should_keep_the_incident_counts_in_the_reduced_fixtures() -> None:
    assert _figure_counts_in_data_block(PILED_PAGE_PATH) == (33, 20)
    assert _figure_counts_in_data_block(REBUILT_PAGE_PATH) == (20, 20)


def test_should_apply_an_edit_whose_old_text_occurs_once() -> None:
    assert page_source_after_edits("<p>old</p>", [{"old_str": "old", "new_str": "new"}]) == (
        "<p>new</p>"
    )


def test_should_leave_the_page_alone_for_an_ambiguous_or_malformed_edit() -> None:
    assert page_source_after_edits("<p>a a</p>", [{"old_str": "a", "new_str": "b"}]) == "<p>a a</p>"
    assert page_source_after_edits("<p>a</p>", [{"old_str": "a"}, "x"]) == "<p>a</p>"
    assert page_source_after_edits("<p>a</p>", None) == "<p>a</p>"


def test_should_apply_no_edit_when_one_edit_of_the_call_misses() -> None:
    all_edits = [{"old_str": "a", "new_str": "x"}, {"old_str": "missing", "new_str": "y"}]
    assert page_source_after_edits("<p>a b</p>", all_edits) == "<p>a b</p>"


def test_should_read_the_page_title() -> None:
    assert page_title("<title> Sample Run </title><p>x</p>") == "Sample Run"
    assert page_title("<p>no title</p>") == ""


def test_should_name_the_record_file_after_the_page_file() -> None:
    assert link_record_path(Path("/work/first-look.html")) == Path(
        "/work/first-look.html.artifact-link.json"
    )


def test_should_find_no_link_for_a_page_with_no_record(tmp_path: Path) -> None:
    assert recorded_page_link(tmp_path / "page.html", PAGE_WITH_ONE_SCREEN) == ""


def test_should_read_the_link_from_the_meta_tag_in_the_page(tmp_path: Path) -> None:
    page_source = f'<meta name="artifact-link" content="{PAGE_LINK}">' + PAGE_WITH_ONE_SCREEN
    assert recorded_page_link(tmp_path / "page.html", page_source) == PAGE_LINK


def test_should_read_the_meta_tag_with_its_attributes_in_either_order(tmp_path: Path) -> None:
    page_source = f"<meta content='{PAGE_LINK}' name='artifact-link'>" + PAGE_WITH_ONE_SCREEN
    assert recorded_page_link(tmp_path / "page.html", page_source) == PAGE_LINK


def test_should_ignore_a_meta_tag_that_holds_no_artifact_link(tmp_path: Path) -> None:
    page_source = '<meta name="artifact-link" content="<link>">' + PAGE_WITH_ONE_SCREEN
    assert recorded_page_link(tmp_path / "page.html", page_source) == ""


def test_should_read_the_link_from_the_record_beside_the_page(tmp_path: Path) -> None:
    page_path = tmp_path / "page.html"
    link_record_path(page_path).write_text(json.dumps({"url": PAGE_LINK, "title": "Other"}))
    assert recorded_page_link(page_path, PAGE_WITH_ONE_SCREEN) == PAGE_LINK


def test_should_find_the_link_of_a_page_renamed_in_its_folder(tmp_path: Path) -> None:
    link_record_path(tmp_path / "page.html").write_text(
        json.dumps({"url": PAGE_LINK, "title": "Sample Run"})
    )
    assert recorded_page_link(tmp_path / "page-v2.html", PAGE_WITH_ONE_SCREEN) == PAGE_LINK
    assert recorded_page_link(tmp_path / "other.html", "<title>Other Page</title>") == ""


def test_should_leave_a_separate_page_with_the_same_title_unlinked(tmp_path: Path) -> None:
    first_page_path = tmp_path / "team-a.html"
    first_page_path.write_text(PAGE_WITH_ONE_SCREEN, encoding="utf-8")
    link_record_path(first_page_path).write_text(
        json.dumps({"url": PAGE_LINK, "title": "Sample Run"})
    )
    assert recorded_page_link(tmp_path / "team-b.html", PAGE_WITH_ONE_SCREEN) == ""


def test_should_name_each_repeated_item_and_its_count() -> None:
    block_reason = format_repeat_reason([{"kind": "image", "item": "screens/home.png", "times": 3}])
    assert "- screens/home.png is drawn 3 times" in block_reason
    assert "Show each item once" in block_reason


def test_should_point_each_message_at_the_installed_rule_text() -> None:
    rule_pointer = full_rule_pointer()
    assert "Republish a page" in rule_pointer
    assert "artifact-page" in rule_pointer and "README.md" in rule_pointer
    assert format_repeat_reason([]).endswith(rule_pointer)


@needs_renderer
def test_should_report_the_eleven_repeated_screens_of_the_piled_page() -> None:
    all_repeats, _ = repeated_items(PILED_PAGE_PATH.read_text(encoding="utf-8"))
    assert all_repeats is not None
    assert len(all_repeats) == 11
    assert sorted(each_repeat["times"] for each_repeat in all_repeats) == [2] * 9 + [3, 3]


@needs_renderer
def test_should_pass_the_rebuilt_page_that_shows_three_draws_of_one_screen() -> None:
    assert repeated_items(REBUILT_PAGE_PATH.read_text(encoding="utf-8")) == ([], "")


@needs_renderer
def test_should_refuse_the_piled_page_that_a_source_tag_count_passes() -> None:
    piled_source = PILED_PAGE_PATH.read_text(encoding="utf-8")
    assert piled_source.count("<img") == 1
    denied_run = _run_gate({"file_path": str(PILED_PAGE_PATH)})
    assert denied_run.returncode == BLOCK_EXIT_CODE
    assert "screens/sample-theme/screen-12.png is drawn 3 times" in denied_run.stderr
    assert _run_gate({"file_path": str(REBUILT_PAGE_PATH)}).returncode == ALLOW_EXIT_CODE


@needs_renderer
def test_should_pass_a_small_icon_used_many_times() -> None:
    icon_row = '<img src="icons/check.png" width="24" height="24" alt="Done">' * 5
    assert repeated_items(icon_row) == ([], "")


@needs_renderer
def test_should_count_an_image_with_no_size_set_as_an_item() -> None:
    page_source = '<img src="screens/home.png" alt="Home"><p>Later</p><img src="screens/home.png" alt="">'
    all_repeats, _ = repeated_items(page_source)
    assert all_repeats == [{"kind": "image", "item": "screens/home.png", "times": 2}]


@needs_renderer
def test_should_count_two_spellings_of_one_image_file_as_one_item() -> None:
    page_source = (
        ITEM_IMAGE_STYLE
        + '<img src="screens/home.png" alt="Home">'
        + '<img src="./screens/home.png" alt="Home again">'
    )
    all_repeats, _ = repeated_items(page_source)
    assert all_repeats == [{"kind": "image", "item": "screens/home.png", "times": 2}]


@needs_renderer
def test_should_count_a_lazy_image_below_the_first_screen() -> None:
    page_source = (
        '<img src="screens/home.png" alt="Home">'
        '<div style="height:4000px"></div>'
        '<img src="screens/home.png" alt="Home" loading="lazy">'
    )
    all_repeats, _ = repeated_items(page_source)
    assert all_repeats == [{"kind": "image", "item": "screens/home.png", "times": 2}]


@needs_renderer
def test_should_pass_a_thumbnail_whose_full_view_is_hidden() -> None:
    page_source = (
        ITEM_IMAGE_STYLE
        + '<img src="screens/home.png" alt="Home">'
        + '<dialog><img src="screens/home.png" alt="Home, full size"></dialog>'
        + '<details><summary>Full size</summary><img src="screens/home.png" alt="Home"></details>'
    )
    assert repeated_items(page_source) == ([], "")


@needs_renderer
def test_should_refuse_a_baseline_drawn_beside_each_variant() -> None:
    page_source = (
        ITEM_IMAGE_STYLE
        + '<img src="screens/baseline.png" alt="Baseline"><img src="screens/variant-a.png" alt="A">'
        + '<img src="screens/baseline.png" alt="Baseline"><img src="screens/variant-b.png" alt="B">'
    )
    all_repeats, _ = repeated_items(page_source)
    assert all_repeats == [{"kind": "image", "item": "screens/baseline.png", "times": 2}]


@needs_renderer
def test_should_refuse_two_drawn_elements_with_one_item_key() -> None:
    page_source = (
        '<article data-item="release-date">Pick a release date</article>'
        '<article data-item="login-test">Flaky login test</article>'
        '<article data-item="release-date">Pick a release date</article>'
        '<article data-item="login-test" hidden>Flaky login test</article>'
    )
    all_repeats, _ = repeated_items(page_source)
    assert all_repeats == [{"kind": "data-item", "item": "release-date", "times": 2}]


@needs_renderer
def test_should_refuse_an_edit_that_adds_a_second_draw_of_a_screen(tmp_path: Path) -> None:
    page_path = tmp_path / "page.html"
    page_path.write_text(PAGE_WITH_ONE_SCREEN + "<footer>End</footer>", encoding="utf-8")
    all_edits = [
        {
            "old_str": "<footer>End</footer>",
            "new_str": SECOND_DRAW_OF_THE_SCREEN + "<footer>End</footer>",
        }
    ]
    assert _run_gate({"file_path": str(page_path)}).returncode == ALLOW_EXIT_CODE
    denied_run = _run_gate({"file_path": str(page_path), "edits": all_edits})
    assert denied_run.returncode == BLOCK_EXIT_CODE
    assert "screens/home.png is drawn 2 times" in denied_run.stderr


@needs_renderer
def test_should_refuse_a_second_link_and_allow_the_recorded_one(tmp_path: Path) -> None:
    page_path = tmp_path / "page.html"
    page_path.write_text(PAGE_WITH_ONE_SCREEN, encoding="utf-8")
    first_publish = _run_gate({"file_path": str(page_path)})
    assert first_publish.returncode == ALLOW_EXIT_CODE
    assert first_publish.stdout == ""
    link_record_path(page_path).write_text(json.dumps({"url": PAGE_LINK, "title": "Sample Run"}))
    denied_run = _run_gate({"file_path": str(page_path)})
    assert denied_run.returncode == BLOCK_EXIT_CODE
    assert PAGE_LINK in denied_run.stderr
    assert "When the user asks for a separate copy" in denied_run.stderr
    assert "page.html.artifact-link.json" in denied_run.stderr
    allowed_run = _run_gate({"file_path": str(page_path), "url": PAGE_LINK})
    assert allowed_run.returncode == ALLOW_EXIT_CODE
    assert (
        REPUBLISH_NOTE in json.loads(allowed_run.stdout)["hookSpecificOutput"]["additionalContext"]
    )


@needs_renderer
def test_should_check_a_page_saved_in_another_text_encoding(tmp_path: Path) -> None:
    page_path = tmp_path / "page.html"
    page_path.write_bytes(
        (PAGE_WITH_ONE_SCREEN + "<p>Caf\u00e9</p>" + SECOND_DRAW_OF_THE_SCREEN).encode("latin-1")
    )
    denied_run = _run_gate({"file_path": str(page_path)})
    assert denied_run.returncode == BLOCK_EXIT_CODE
    assert "screens/home.png is drawn 2 times" in denied_run.stderr


def test_should_allow_reads_assets_and_other_tools(tmp_path: Path) -> None:
    page_path = tmp_path / "page.html"
    page_path.write_text(PAGE_WITH_ONE_SCREEN + SECOND_DRAW_OF_THE_SCREEN, encoding="utf-8")
    assert _run_gate({"action": "read", "url": PAGE_LINK}).returncode == ALLOW_EXIT_CODE
    assert _run_gate({"file_path": str(page_path), "asset": True}).returncode == ALLOW_EXIT_CODE
    assert _run_gate({"file_path": str(tmp_path / "missing.html")}).returncode == ALLOW_EXIT_CODE
