"""Put the eval flow, its fixture project and the hooks helpers on the import path."""

import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent

for each_import_root in (
    flow_directory,
    flow_directory / "fixture",
    flow_directory.parents[2] / "packages" / "claude-dev-env" / "hooks",
):
    if str(each_import_root) not in sys.path:
        sys.path.insert(0, str(each_import_root))
