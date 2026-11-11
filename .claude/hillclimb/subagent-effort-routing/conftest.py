"""Put this flow and the shared session helpers on the import path."""

import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent

for each_import_root in (
    flow_directory,
    flow_directory.parent / "features-start-with-an-eval",
):
    if str(each_import_root) not in sys.path:
        sys.path.insert(0, str(each_import_root))
