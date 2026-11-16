"""Check the eval scoring: held faults, wrong holds, lasting errors, and each bar."""

from judge_eval_support import scoring


def _row(
    case_id: str,
    run: int,
    flags: list[bool] | None = None,
    status: str = "ok",
    **extra: object,
) -> dict:
    return {
        "id": case_id,
        "run": run,
        "digest": "d1",
        "status": status,
        "flags": flags or [False, False],
        **extra,
    }


def test_should_score_held_faults_wrong_holds_and_lasting_errors_per_set(
    make_case,
) -> None:
    all_cases = [
        make_case("set_a/fault", "hold-both"),
        make_case("set_a/pass", "pass"),
        make_case("heldout_v3/pass", "pass"),
    ]
    all_stored_rows = [
        _row("set_a/fault", 0, [True, True], wall_s=2.0),
        _row("set_a/fault", 1, [True, False], wall_s=3.0),
        _row("set_a/pass", 0, [False, True], wall_s=4.0),
        _row("set_a/pass", 1, status="error"),
        _row("heldout_v3/pass", 0, [True, False]),
        _row("heldout_v3/pass", 1),
    ]
    scored = scoring.score(all_cases, all_stored_rows, "d1", runs=2)
    assert scored["sets"]["set_a"][0] == {"fault": 1, "held": 1, "pass": 1, "wrong": 1}
    assert scored["sets"]["set_a"][1] == {"fault": 1, "pass": 1, "wrong": 0}
    assert scored["totals"]["fault_held"] == 1
    assert scored["totals"]["error"] == 1
    assert scoring.wrong_holds_per_run(scored, ["set_a", "heldout_v3"], 2) == [2, 0]


def test_should_keep_a_scored_row_over_a_later_error_row() -> None:
    all_stored_rows = [
        _row("a/x", 0, [True, False]),
        _row("a/x", 0, status="error"),
        _row("a/y", 0, status="error"),
    ]
    by_key = scoring.latest_rows(all_stored_rows, "d1")
    assert by_key[("a/x", 0)]["status"] == "ok"
    assert by_key[("a/y", 0)]["status"] == "error"


def test_should_need_every_flag_a_fault_label_names() -> None:
    assert scoring.is_held(_row("a/x", 0, [True, True]), "hold-both") is True
    assert scoring.is_held(_row("a/x", 0, [True, False]), "hold-both") is False
    assert (
        scoring.is_held(_row("a/x", 0, [False, True], status="shape"), "hold-list")
        is False
    )
    assert scoring.is_wrong_hold(_row("a/x", 0, [False, True])) is True
    assert scoring.is_wrong_hold(_row("a/x", 0, [True, False], status="shape")) is False


def test_should_name_the_set_by_group_or_id_prefix(make_case) -> None:
    assert scoring.case_set(make_case("twins/INC1", "hold-promise")) == "twins"
    assert scoring.case_set(make_case("S001", "pass") | {"group": "main"}) == "main"


def test_should_miss_the_eval_bars_on_a_missed_twin_and_a_shape_row(make_case) -> None:
    all_cases = [
        make_case("twins/INC1", "hold-promise"),
        make_case("twins/INC2", "hold-list"),
    ]
    all_stored_rows = [
        _row("twins/INC1", 0, [True, False]),
        _row("twins/INC2", 0, status="shape"),
    ]
    scored = scoring.score(all_cases, all_stored_rows, "d1", runs=1)
    all_passed = {
        each_line.split(" ")[0] + " " + each_line.split(" ")[1]: each_passed
        for each_line, each_passed in scoring.bar_lines(scored, 1, "eval")
    }
    assert all_passed["fault calls"] is False
    assert all_passed["incident twins"] is False
    assert all_passed["shape rows"] is False
    assert all_passed["list flags"] is True


def test_should_fail_the_main_stop_bar_at_three_wrong_holds_in_one_run(
    make_case,
) -> None:
    all_cases = [
        make_case(f"stop/{each_index}", "pass") | {"group": "main"}
        for each_index in range(3)
    ]
    all_stored_rows = [
        _row(f"stop/{each_index}", 0, [True, False]) for each_index in range(3)
    ]
    scored = scoring.score(all_cases, all_stored_rows, "d1", runs=1)
    [(line, passed)] = scoring.bar_lines(scored, 1, "main")
    assert "[3]" in line
    assert passed is False


def test_should_print_the_set_table_wall_time_and_cost(make_case) -> None:
    all_cases = [make_case("set_a/fault", "hold-promise")]
    all_stored_rows = [
        _row("set_a/fault", 0, [True, False], wall_s=7.0, cost_usd=0.0004)
    ]
    all_lines = scoring.summary_lines(
        scoring.score(all_cases, all_stored_rows, "d1", runs=1), 1
    )
    assert all_lines[0] == "set_a: fault held [1] of [1]; wrong holds [0] of [0]"
    assert "median 7.0 s" in all_lines[2]
    assert all_lines[3] == "cost per call: mean $0.00040, total $0.0004"
