"""Reach the cloud session check from the scripts this directory deploys.

``hooks_constants`` is reachable only through the deployed ``hooks``
directory, so this module puts that directory on the end of ``sys.path``
and re-exports the check a caller asks for::

    from cloud_session_access import is_cloud_session
"""

from __future__ import annotations

import sys
from pathlib import Path

_cloud_session_hooks_directory = str(Path(__file__).resolve().parents[1] / "hooks")
if _cloud_session_hooks_directory not in sys.path:
    sys.path.append(_cloud_session_hooks_directory)

from hooks_constants.cloud_session import is_cloud_session

__all__ = ["is_cloud_session"]
