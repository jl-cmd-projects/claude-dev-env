"""Behavior tests for eval run selection."""

import json
import sys
from pathlib import Path

flow_directory = str(Path(__file__).resolve().parent)
if flow_directory not in sys.path:
    sys.path.insert(0, flow_directory)

from run import _pending_runs
from session_eval_support.config.constants import RESULTS_FILE_NAME


def test_pending_runs_skip_completed_case_and_rep(tmp_path: Path) -> None:
    (tmp_path / RESULTS_FILE_NAME).write_text(
        json.dumps({"prompt_id": "case-a", "rep": 0}) + "\n"
    )
    cases = [{"id": "case-a"}, {"id": "case-b"}]

    assert _pending_runs(cases, 2, tmp_path) == [
        (cases[0], 1),
        (cases[1], 0),
        (cases[1], 1),
    ]
