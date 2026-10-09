"""Names, limits and messages for the artifact_dark_mode_gate PreToolUse hook."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "ALLOW_EXIT_CODE",
    "ALL_SKIPPED_PUBLISH_INPUT_KEYS",
    "ARTIFACT_ACTION_INPUT_KEY",
    "ARTIFACT_FILE_PATH_INPUT_KEY",
    "ARTIFACT_PUBLISH_ACTION",
    "ARTIFACT_TOOL_NAME",
    "BLOCK_EXIT_CODE",
    "DARK_MODE_FAILURE_HEADER",
    "GATE_EVENT_NAME",
    "HTML_FILE_SUFFIX",
    "PUBLISH_SKELETON_PREFIX",
    "RENDERER_MISSING_EXIT_CODE",
    "RENDERER_MISSING_HEADER",
    "RENDERER_SCRIPT_PATH",
    "RENDERER_TIMEOUT_SECONDS",
    "RETRY_INSTRUCTION",
]

ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
RENDERER_MISSING_EXIT_CODE = 3
RENDERER_TIMEOUT_SECONDS = 50
ARTIFACT_TOOL_NAME = "Artifact"
ARTIFACT_ACTION_INPUT_KEY = "action"
ARTIFACT_PUBLISH_ACTION = "publish"
ARTIFACT_FILE_PATH_INPUT_KEY = "file_path"
ALL_SKIPPED_PUBLISH_INPUT_KEYS = ("asset", "type_url")
HTML_FILE_SUFFIX = ".html"
GATE_EVENT_NAME = "PreToolUse"
RENDERER_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "blocking" / "artifact_dark_mode_render.cjs"
)
PUBLISH_SKELETON_PREFIX = (
    "<!doctype html><html><head><meta charset=utf8>"
    '<meta name=viewport content="width=device-width,initial-scale=1">'
    "<style>:root{color-scheme:light}body{margin:0;padding:0;"
    "font:14px -apple-system,BlinkMacSystemFont,sans-serif;"
    "background:#faf9f5;color:#141413}img{max-width:100%}"
    "[hidden]:not([hidden=until-found i]){display:none!important}</style>"
    "</head><body>\n"
)
DARK_MODE_FAILURE_HEADER = (
    "Inside the artifact publish wrapper, this page has unreadable text when the viewer uses dark mode.\n"
)
RENDERER_MISSING_HEADER = "The page did not render for its contrast check before publish: "
RETRY_INSTRUCTION = (
    "\nThe publish wrapper pins body to a light background and dark text. Set body background and"
    " color from the page's theme tokens, for example body{background:var(--paper);color:var(--ink)},"
    ' so both flip under prefers-color-scheme: dark and data-theme="dark". Then publish again.'
)
