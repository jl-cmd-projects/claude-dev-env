"""Tell a hook whether it runs inside a Claude Code cloud session."""

from __future__ import annotations

import os

from hooks_constants.cloud_session_constants import (
    CLOUD_SESSION_ENV_TRUE_VALUE,
    CLOUD_SESSION_ENV_VAR,
)

__all__ = ["is_cloud_session"]


def is_cloud_session() -> bool:
    """Return True when ``CLAUDE_CODE_REMOTE`` is ``true``, whatever its case or padding."""
    return os.environ.get(CLOUD_SESSION_ENV_VAR, "").strip().lower() == CLOUD_SESSION_ENV_TRUE_VALUE
