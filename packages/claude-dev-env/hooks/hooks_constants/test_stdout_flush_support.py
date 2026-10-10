"""Shared stdout stand-in for hook emitter tests that check flush behavior."""

from __future__ import annotations

from io import StringIO


class FlushRecordingStream(StringIO):
    """StringIO that records the full buffer text at each flush call."""

    def __init__(self) -> None:
        super().__init__()
        self.flushed_text: list[str] = []

    def flush(self) -> None:
        self.flushed_text.append(self.getvalue())
        super().flush()
