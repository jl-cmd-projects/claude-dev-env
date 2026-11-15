from pathlib import Path

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
