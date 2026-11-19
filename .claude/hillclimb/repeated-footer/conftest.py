"""Put this flow on the import path."""

import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent

if str(flow_directory) not in sys.path:
    sys.path.insert(0, str(flow_directory))
