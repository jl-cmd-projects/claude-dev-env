"""Names for the marker files that let a hook show its fixed text once per session.

Groups: the payload keys the helper reads, the marker file name parts, and the
transcript entries that mark a compaction in Claude Code and in Codex.
"""

from __future__ import annotations

SESSION_ID_KEY = "session_id"
AGENT_ID_KEY = "agent_id"
TRANSCRIPT_PATH_KEY = "transcript_path"

ONCE_MARKER_FILE_PREFIX = "claude-once-"
ONCE_MARKER_FILE_SUFFIX = ".marker"
ONCE_MARKER_NAME_SEPARATOR = "."
EXCLUSIVE_CREATE_MODE = "x"
WHOLE_SESSION_MARKER_PART = "session"

TRANSCRIPT_READ_MODE = "rb"
CLAUDE_COMPACTION_FIELD = "subtype"
CLAUDE_COMPACTION_VALUE = "compact_boundary"
CODEX_COMPACTION_FIELD = "type"
CODEX_COMPACTION_VALUE = "compacted"
ALL_COMPACTION_ENTRY_FIELDS = (
    (CLAUDE_COMPACTION_FIELD, CLAUDE_COMPACTION_VALUE),
    (CODEX_COMPACTION_FIELD, CODEX_COMPACTION_VALUE),
)
ALL_COMPACTION_LINE_MARKERS = tuple(
    each_value.encode() for _, each_value in ALL_COMPACTION_ENTRY_FIELDS
)
