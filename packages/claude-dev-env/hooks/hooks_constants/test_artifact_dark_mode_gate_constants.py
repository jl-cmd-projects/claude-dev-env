"""Behavioral tests for the artifact page gate's paths and publish wrapper."""

from hooks_constants.artifact_dark_mode_gate_constants import (
    PUBLISH_SKELETON_PREFIX,
    RENDERER_SCRIPT_PATH,
)


def test_renderer_path_names_the_packaged_render_script() -> None:
    assert RENDERER_SCRIPT_PATH.is_file()
    assert RENDERER_SCRIPT_PATH.suffix == ".cjs"


def test_publish_wrapper_pins_body_light_and_opens_the_body() -> None:
    assert "body{margin:0;padding:0;" in PUBLISH_SKELETON_PREFIX
    assert "background:#faf9f5;color:#141413" in PUBLISH_SKELETON_PREFIX
    assert PUBLISH_SKELETON_PREFIX.endswith("<body>\n")
