"""Check that the eval constants match the bars and paths the flow's _state.json names."""

import json

from judge_eval_support.config import constants


def test_should_match_the_bars_in_the_state_file() -> None:
    state = json.loads(
        (constants.FLOW_ROOT / "_state.json").read_text(encoding="utf-8")
    )
    assert state["bars"] == {
        "fault_held_share": constants.FAULT_HELD_SHARE_BAR,
        "incident_twins_held_runs": constants.DEFAULT_RUNS,
        "wrong_holds_per_run_outside_heldout_v3": constants.OTHER_PASS_WRONG_HOLD_BAR,
        "wrong_holds_per_run_heldout_v3": constants.SEPARATE_PASS_WRONG_HOLD_BAR,
        "wrong_holds_per_run_main_stops_local": constants.MAIN_STOP_WRONG_HOLD_BAR,
        "incident1_list_flags": 0,
        "shape_rows": 0,
    }


def test_should_point_at_the_shipped_judge_files() -> None:
    assert constants.CASES_FILE.is_file()
    for each_path in constants.ALL_DIGEST_SOURCES:
        assert each_path.is_file(), each_path
