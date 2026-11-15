"""Behavioral tests for the artifact page gate's paths and publish wrapper."""

from hooks_constants.artifact_dark_mode_gate_constants import (
    BLOCKING_HOOKS_DIRECTORY,
    PUBLISH_SKELETON_PREFIX,
    RENDERER_SCRIPT_PATH,
)


def test_renderer_path_names_the_packaged_render_script() -> None:
    assert RENDERER_SCRIPT_PATH.is_file()
    assert RENDERER_SCRIPT_PATH.suffix == ".cjs"


def test_blocking_directory_holds_the_gate_that_runs_the_renderer() -> None:
    assert (BLOCKING_HOOKS_DIRECTORY / "artifact_dark_mode_gate.py").is_file()
    assert RENDERER_SCRIPT_PATH.parent == BLOCKING_HOOKS_DIRECTORY


def test_publish_wrapper_pins_body_light_and_opens_the_body() -> None:
    assert "body{margin:0;padding:0;" in PUBLISH_SKELETON_PREFIX
    assert "background:#faf9f5;color:#141413" in PUBLISH_SKELETON_PREFIX
    assert PUBLISH_SKELETON_PREFIX.endswith("<body>\n")
