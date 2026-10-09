"""Behavior tests for the artifact dark mode publish gate."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from blocking.artifact_dark_mode_gate import (
    render_findings,
    format_block_reason,
    published_page_path,
    wrap_in_publish_skeleton,
)
from hooks_constants.artifact_dark_mode_gate_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    PUBLISH_SKELETON_PREFIX,
)

GATE_SCRIPT_PATH = Path(__file__).resolve().parent / "artifact_dark_mode_gate.py"
THEME_COLOR_STYLES = (
    "<style>:root{--paper:#faf9f5;--ink:#141413;color-scheme:light dark}"
    "@media (prefers-color-scheme: dark){:root:not([data-theme=light]){--paper:#262624;--ink:#faf9f5}}"
    ":root[data-theme=dark]{--paper:#262624;--ink:#faf9f5}"
    "html{background:var(--paper);color:var(--ink)}h1{color:var(--ink)}</style>"
)
PAGE_WITH_TOKENS_ON_HTML_ONLY = THEME_COLOR_STYLES + "<h1>Weekly totals</h1><p>Three runs today.</p>"
PAGE_WITH_THEMED_BODY = (
    THEME_COLOR_STYLES + "<style>body{background:var(--paper);color:var(--ink)}</style>"
    "<h1>Weekly totals</h1><p>Three runs today.</p>"
)


def _renderer_available() -> bool:
    if shutil.which("node") is None:
        return False
    findings_by_signal, _ = render_findings("<p>probe</p>")
    return findings_by_signal is not None


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


def test_should_return_the_page_path_for_an_html_publish() -> None:
    assert published_page_path("Artifact", {"file_path": "/tmp/page.html"}) == Path(
        "/tmp/page.html"
    )


def test_should_skip_reads_assets_typed_creates_and_other_tools() -> None:
    assert published_page_path("Artifact", {"action": "read", "url": "x"}) is None
    assert published_page_path("Artifact", {"file_path": "/tmp/logo.html", "asset": True}) is None
    assert published_page_path("Artifact", {"file_path": "/tmp/data.html", "type_url": "x"}) is None
    assert published_page_path("Artifact", {"file_path": "/tmp/notes.md"}) is None
    assert published_page_path("Write", {"file_path": "/tmp/page.html"}) is None


def test_should_put_the_page_after_the_skeleton_that_pins_body_light() -> None:
    wrapped_page = wrap_in_publish_skeleton("<p>x</p>")
    assert wrapped_page == PUBLISH_SKELETON_PREFIX + "<p>x</p>"
    assert "background:#faf9f5" in wrapped_page


def test_should_list_each_finding_under_its_dark_signal() -> None:
    block_reason = format_block_reason(
        {"prefers-color-scheme: dark": ['text "A" has contrast 1.00:1']}
    )
    assert "Under prefers-color-scheme: dark:" in block_reason
    assert '- text "A" has contrast 1.00:1' in block_reason
    assert "body{background:var(--paper);color:var(--ink)}" in block_reason


@needs_renderer
def test_should_fail_a_page_that_themes_html_but_not_body() -> None:
    findings_by_signal, _ = render_findings(PAGE_WITH_TOKENS_ON_HTML_ONLY)
    assert set(findings_by_signal) == {"prefers-color-scheme: dark", 'data-theme="dark"'}
    assert any(
        "Weekly totals" in each_finding for each_finding in findings_by_signal['data-theme="dark"']
    )


@needs_renderer
def test_should_pass_a_page_that_themes_body() -> None:
    assert render_findings(PAGE_WITH_THEMED_BODY) == ({}, "")


@needs_renderer
def test_should_deny_and_then_allow_the_publish_call(tmp_path: Path) -> None:
    page_path = tmp_path / "report.html"
    page_path.write_text(PAGE_WITH_TOKENS_ON_HTML_ONLY, encoding="utf-8")
    denied_run = _run_gate({"action": "publish", "file_path": str(page_path)})
    assert denied_run.returncode == BLOCK_EXIT_CODE
    assert "has unreadable text" in denied_run.stderr
    page_path.write_text(PAGE_WITH_THEMED_BODY, encoding="utf-8")
    assert _run_gate({"file_path": str(page_path)}).returncode == ALLOW_EXIT_CODE
