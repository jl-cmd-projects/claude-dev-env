from __future__ import annotations

from pathlib import Path

import pytest

from directory_link_test_support import create_directory_link


def test_should_link_a_folder_to_its_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "marker.txt").write_text("found", encoding="utf-8")

    create_directory_link(from_link=tmp_path / "link", to_target=target)

    assert (tmp_path / "link" / "marker.txt").read_text(encoding="utf-8") == "found"


def test_should_skip_when_the_link_cannot_be_created(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    occupied = tmp_path / "occupied"
    occupied.mkdir()

    with pytest.raises(pytest.skip.Exception):
        create_directory_link(from_link=occupied, to_target=target)
