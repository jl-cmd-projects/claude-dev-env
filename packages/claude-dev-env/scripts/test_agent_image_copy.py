"""Behavior tests for the agent image copy script."""

import argparse
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_image_copy


def test_capped_size_should_keep_the_aspect_ratio() -> None:
    assert agent_image_copy.capped_size(1440, 2560) == (288, 512)
    assert agent_image_copy.capped_size(2000, 1000) == (512, 256)
    assert agent_image_copy.capped_size(300, 200) == (300, 200)


def test_visual_tokens_should_count_28_pixel_patches() -> None:
    assert agent_image_copy.visual_tokens(1440, 2560) == 4784
    assert agent_image_copy.visual_tokens(288, 512) == 209


def test_parse_crop_box_should_refuse_three_numbers() -> None:
    assert agent_image_copy.parse_crop_box("0,0,10,20") == (0, 0, 10, 20)
    with pytest.raises(argparse.ArgumentTypeError):
        agent_image_copy.parse_crop_box("0,0,10")


def test_write_agent_copy_should_write_a_capped_newer_file(tmp_path: Path) -> None:
    source_path = tmp_path / "preview.png"
    Image.new("RGB", (1440, 2560), "white").save(source_path)
    copy_path = agent_image_copy.write_agent_copy(source_path)
    assert copy_path.name == "preview.agent.png"
    with Image.open(copy_path) as copy_image:
        assert copy_image.size == (288, 512)
    assert copy_path.stat().st_mtime >= source_path.stat().st_mtime


def test_write_agent_copy_should_crop_before_scaling(tmp_path: Path) -> None:
    source_path = tmp_path / "preview.png"
    Image.new("RGB", (1440, 2560), "white").save(source_path)
    copy_path = agent_image_copy.write_agent_copy(source_path, (0, 0, 720, 640))
    with Image.open(copy_path) as copy_image:
        assert copy_image.size == (512, 455)


def test_write_agent_copy_should_write_a_cmyk_jpeg_as_rgb(tmp_path: Path) -> None:
    source_path = tmp_path / "print.jpg"
    Image.new("CMYK", (1000, 800)).save(source_path)
    copy_path = agent_image_copy.write_agent_copy(source_path)
    with Image.open(copy_path) as copy_image:
        assert copy_image.mode == "RGB"
        assert copy_image.size == (512, 410)


def test_write_agent_copy_should_follow_the_exif_orientation(tmp_path: Path) -> None:
    source_path = tmp_path / "phone.jpg"
    source_image = Image.new("RGB", (1000, 600), "white")
    all_exif_tags = source_image.getexif()
    all_exif_tags[0x0112] = 6
    source_image.save(source_path, exif=all_exif_tags)
    copy_path = agent_image_copy.write_agent_copy(source_path)
    with Image.open(copy_path) as copy_image:
        assert copy_image.size == (307, 512)


def test_main_should_print_the_copy_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_path = tmp_path / "shot.png"
    Image.new("RGB", (1600, 900), "white").save(source_path)
    assert agent_image_copy.main([str(source_path)]) == 0
    assert "shot.agent.png 512x288 about 209 tokens" in capsys.readouterr().out
