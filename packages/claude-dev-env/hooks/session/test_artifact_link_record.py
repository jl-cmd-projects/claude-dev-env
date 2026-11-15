"""Behavior tests for the hook that records a published page's link beside the page."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from blocking.artifact_current_page_gate import link_record_path, recorded_page_link
from session.artifact_link_record import published_link, record_page_link

RECORD_SCRIPT_PATH = Path(__file__).resolve().parent / "artifact_link_record.py"
PAGE_LINK = "https://claude.ai/artifact/SamplePageLink01"
PAGE_SOURCE = "<title>Sample Run</title><p>One screen.</p>"


def _run_record(tool_input: dict[str, object], tool_response: object) -> int:
    completed_run = subprocess.run(
        [sys.executable, str(RECORD_SCRIPT_PATH)],
        input=json.dumps(
            {"tool_name": "Artifact", "tool_input": tool_input, "tool_response": tool_response}
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed_run.stdout == ""
    return completed_run.returncode


def test_should_take_the_link_the_call_passed() -> None:
    assert published_link({"url": PAGE_LINK}, "Updated the page.") == PAGE_LINK


def test_should_take_the_link_the_result_names() -> None:
    assert published_link({}, f"Published to {PAGE_LINK} (private).") == PAGE_LINK
    code_link = "https://claude.ai/code/artifact/0e557edc-f0c7-4382-8568-aee7ab02950b"
    assert published_link({}, [{"type": "text", "text": f"Live at {code_link}."}]) == code_link


def test_should_take_the_url_field_of_a_publish_result_over_another_link_in_it() -> None:
    publish_result = {
        "note": "Started from https://claude.ai/artifact/SomeOtherPage01",
        "url": PAGE_LINK,
        "title": "Sample Run",
        "seq": 1,
    }
    assert published_link({}, publish_result) == PAGE_LINK


def test_should_find_no_link_in_a_result_that_names_none() -> None:
    assert published_link({}, "The publish was refused.") == ""


def test_should_take_a_link_whose_id_holds_an_underscore() -> None:
    underscore_link = "https://claude.ai/artifact/Ab_12Cd"
    assert published_link({}, f"Published to {underscore_link}.") == underscore_link


def test_should_record_nothing_when_the_result_text_names_two_links() -> None:
    result_text = f"Copied from https://claude.ai/artifact/SourcePage01 to {PAGE_LINK}."
    assert published_link({}, result_text) == ""
    assert published_link({}, f"Published to {PAGE_LINK}. Open {PAGE_LINK}.") == PAGE_LINK


def test_should_write_the_link_and_title_beside_the_page(tmp_path: Path) -> None:
    page_path = tmp_path / "first-look.html"
    page_path.write_text(PAGE_SOURCE, encoding="utf-8")
    record_page_link(page_path, PAGE_LINK)
    assert json.loads(link_record_path(page_path).read_text(encoding="utf-8")) == {
        "url": PAGE_LINK,
        "title": "Sample Run",
    }


def test_should_write_no_record_for_a_page_that_is_gone(tmp_path: Path) -> None:
    missing_page_path = tmp_path / "missing.html"
    record_page_link(missing_page_path, PAGE_LINK)
    assert not link_record_path(missing_page_path).exists()


def test_should_record_a_first_publish_so_the_gate_finds_its_link(tmp_path: Path) -> None:
    page_path = tmp_path / "first-look.html"
    page_path.write_text(PAGE_SOURCE, encoding="utf-8")
    assert _run_record({"file_path": str(page_path)}, f"Published: {PAGE_LINK}") == 0
    assert recorded_page_link(page_path, PAGE_SOURCE) == PAGE_LINK


def test_should_write_no_record_for_a_read_or_a_result_with_no_link(tmp_path: Path) -> None:
    page_path = tmp_path / "first-look.html"
    page_path.write_text(PAGE_SOURCE, encoding="utf-8")
    assert _run_record({"action": "read", "url": PAGE_LINK}, PAGE_SOURCE) == 0
    assert _run_record({"file_path": str(page_path)}, "The publish was refused.") == 0
    assert not link_record_path(page_path).exists()
