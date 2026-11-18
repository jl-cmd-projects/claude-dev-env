"""Frozen study design, acquisition protocol and timing units."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
ALL_CASE_FILES = ("cases.json", "sustained_case.json")
ALL_CASES = {name: case for file in ALL_CASE_FILES for name, case in json.loads((HERE / file).read_text()).items()}
BASE_DIGEST = "891bdb4c8d3ac3b7771ba6f653279ccf299ddb2ca0c4fd8748e2e17b71e7a11f"
ANCHOR = "# Autonomy and persistence\n"
CONFIG_CLIENT = "active_eval/config/client.py"
ORIGINAL_CLIENT = "266bbe5c2c35a941473bc451348f158927ad3de8b134934650bc94db2554e585"
PREVIOUS_DELIVERIES = 60
PREVIOUS_BATCHES = 14
STALL_CYCLE = 2
MS_PER_SECOND = 1000
JSON_INDENT = 2
REPETITIONS = 2
ID_BYTES = 6
REQUEST_LIMIT = 8192
POLL_SECONDS = 0.025
JSON_SUFFIX = ".json"
GRANT_SUFFIX = ".grant"
WORD_SEPARATOR = " "
DESK_USAGE = "\nRun python console.py OPERATION [ARGUMENT ...] in this directory.\n"
BASELINE_ARM = "baseline"
CANDIDATE_ARM = "candidate"
FROZEN_PARAGRAPH = "76ad400468e048058a784a11bcecd35a0b8668ebf60a5760cdc38a8f2f602225"
SOURCE_REVISION = "3ab5949a8ea9c1ad11280e8e9a524bee2587bb8a"
WORKER_MODEL = "gpt-6.2-sol"
REASONING_EFFORT = "high"
