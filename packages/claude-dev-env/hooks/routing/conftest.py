"""Add hooks/routing and hooks/ to sys.path for every test collected under this directory."""

import sys
from pathlib import Path

_ROUTING_DIRECTORY = str(Path(__file__).resolve().parent)
_HOOKS_DIRECTORY = str(Path(_ROUTING_DIRECTORY).parent)
for each_directory in (_ROUTING_DIRECTORY, _HOOKS_DIRECTORY):
    if each_directory not in sys.path:
        sys.path.insert(0, each_directory)
