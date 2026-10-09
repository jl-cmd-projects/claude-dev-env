"""Names and refusal text for the artifact_look_gate PreToolUse hook."""

from __future__ import annotations

ARTIFACT_TOOL_NAME = "Artifact"
ARTIFACT_ACTION_INPUT_KEY = "action"
ARTIFACT_PUBLISH_ACTION = "publish"
ARTIFACT_ASSET_INPUT_KEY = "asset"
FILE_PATH_INPUT_KEY = "file_path"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
TRANSCRIPT_PATH_KEY = "transcript_path"
IMAGE_READING_TOOL_NAME = "Read"
ALL_IMAGE_FILE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
ALL_PAGE_FILE_SUFFIXES = (".html", ".htm")
TRANSCRIPT_ENCODING = "utf-8"
TRANSCRIPT_DECODE_ERRORS = "replace"
ASSISTANT_ENTRY_TYPE = "assistant"
USER_ENTRY_TYPE = "user"
TOOL_USE_BLOCK_TYPE = "tool_use"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
ENTRY_TIMESTAMP_KEY = "timestamp"
PRE_TOOL_USE_EVENT_NAME = "PreToolUse"
DENY_DECISION = "deny"
UNSEEN_PAGE_REASON_TEMPLATE = (
    "This page has not been looked at since it was last written. Render it "
    "and look at the picture before you publish: take a screenshot with a "
    "headless browser, for example `chromium --headless --screenshot=page.png "
    "--window-size=800,900 file://{page_path}`, then open page.png with the "
    "Read tool and check it against the ask. Fix what the picture shows, take "
    "a new screenshot, and publish again."
)
