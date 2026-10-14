"""Put the eval flow and its fixture project on the import path for every test here."""

import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent

for each_import_root in (flow_directory, flow_directory / "fixture"):
    if str(each_import_root) not in sys.path:
        sys.path.insert(0, str(each_import_root))
