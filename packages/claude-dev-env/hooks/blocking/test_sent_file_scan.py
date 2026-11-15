import time
from pathlib import Path

import sent_file_question_detector
import sent_file_scan


def test_sent_file_scan_text_should_join_the_start_and_end_of_a_large_file(tmp_path: Path) -> None:
    file_path = tmp_path / "large.md"
    file_path.write_text("A" * 200000 + "é" + "B" * 200000, encoding="utf-8")
    scan_text = sent_file_scan.sent_file_scan_text("large.md", str(tmp_path))
    assert scan_text is not None
    head_text, tail_text = scan_text.split("\n\n")
    assert head_text == "A" * 131072
    assert tail_text.endswith("B" * 1000)
    assert len(tail_text) <= 131072
    assert sent_file_scan.sent_file_scan_text("small.md", str(tmp_path)) is None
    (tmp_path / "small.md").write_text("Short note.\n", encoding="utf-8")
    assert sent_file_scan.sent_file_scan_text("small.md", str(tmp_path)) == "Short note.\n"


def test_sent_file_scan_text_should_skip_a_file_that_is_not_utf8_text(tmp_path: Path) -> None:
    (tmp_path / "nul.md").write_bytes(b"Note\x00text")
    (tmp_path / "latin.md").write_bytes(b"Caf\xe9 notes")
    (tmp_path / "shot.png").write_text("Should I?", encoding="utf-8")
    assert sent_file_scan.sent_file_scan_text("nul.md", str(tmp_path)) is None
    assert sent_file_scan.sent_file_scan_text("latin.md", str(tmp_path)) is None
    assert sent_file_scan.sent_file_scan_text("shot.png", str(tmp_path)) is None


def test_sent_file_is_partly_read_should_name_only_a_text_file_over_the_limit(
    tmp_path: Path,
) -> None:
    (tmp_path / "large.md").write_text("A" * 262145, encoding="utf-8")
    (tmp_path / "limit.md").write_text("A" * 262144, encoding="utf-8")
    (tmp_path / "large.png").write_bytes(b"A" * 262145)
    assert sent_file_scan.sent_file_is_partly_read("large.md", str(tmp_path)) is True
    assert sent_file_scan.sent_file_is_partly_read("limit.md", str(tmp_path)) is False
    assert sent_file_scan.sent_file_is_partly_read("large.png", str(tmp_path)) is False
    assert sent_file_scan.sent_file_is_partly_read("missing.md", str(tmp_path)) is False


def test_plain_page_text_should_strip_tags_in_one_pass() -> None:
    page_markup = (
        "<h2>Plan</h2><p>Should I <b>merge</b> it?</p>"
        "<script>var x = 'Do you want this?';</script><pre>Can I go?</pre><p>A &amp; B</p>"
    )
    plain_text = sent_file_scan.plain_page_text(page_markup)
    assert "# Plan" in plain_text
    assert "Should I merge it?" in plain_text
    assert "Do you want this?" not in plain_text
    assert "Can I go?" not in plain_text
    assert "A & B" in plain_text
    assert (
        sent_file_question_detector.question_for_user(plain_text, is_html=False)
        == "Should I merge it?"
    )


def test_plain_page_text_should_read_unclosed_script_openers_in_linear_time() -> None:
    started_at = time.perf_counter()
    plain_text = sent_file_scan.plain_page_text("<p>Should I merge it?</p>" + "<script " * 30000)
    assert time.perf_counter() - started_at < 1
    assert "Should I merge it?" in plain_text
