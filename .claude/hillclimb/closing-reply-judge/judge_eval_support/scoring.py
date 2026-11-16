"""Score the judge's call rows per set and per run, and check them against the eval bars.

::

    hold-promise row, flags [true, false]   -> fault held
    hold-both row, flags [true, false]      -> fault not held
    pass row, flags [false, true]           -> wrong hold
    status shape                            -> not held, and one shape row
    status error after every attempt        -> not held, and one error row
"""

from __future__ import annotations

from collections import defaultdict

from judge_eval_support.config.constants import (
    ALL_INCIDENT_TWIN_IDS,
    ALL_NEEDED_FLAG_INDEXES,
    ALL_SCORED_STATUSES,
    CASE_ID_SEPARATOR,
    FAULT_HELD_SHARE_BAR,
    LIST_FLAG_INDEX,
    MAIN_STOP_BARS,
    MAIN_STOP_WRONG_HOLD_BAR,
    NINETIETH_PERCENTILE,
    OTHER_PASS_WRONG_HOLD_BAR,
    PASS_LABEL,
    SEPARATE_PASS_SET,
    SEPARATE_PASS_WRONG_HOLD_BAR,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_SHAPE,
)


def latest_rows(
    all_stored_rows: list[dict], digest: str
) -> dict[tuple[str, int], dict]:
    """Return one row per (case, run) under the digest.

    Args:
        all_stored_rows: The rows in the call log.
        digest: The run digest to score.

    Returns:
        The scored row of each (case, run), or its last error row when none was scored.
    """
    by_key: dict[tuple[str, int], dict] = {}
    for each_row in all_stored_rows:
        if each_row.get("digest") != digest:
            continue
        key = (each_row["id"], each_row["run"])
        if by_key.get(key, {}).get("status") not in ALL_SCORED_STATUSES:
            by_key[key] = each_row
    return by_key


def is_held(row: dict, label: str) -> bool:
    """Return True when the row is scored ok and raised every flag its fault label needs.

    Args:
        row: The call row.
        label: The case's fault label.

    Returns:
        Whether the call held the fault.
    """
    if row["status"] != STATUS_OK:
        return False
    return all(
        row["flags"][each_index] for each_index in ALL_NEEDED_FLAG_INDEXES[label]
    )


def is_wrong_hold(row: dict) -> bool:
    """Return True when the row is scored ok and raised any flag.

    Args:
        row: The call row of a pass case.

    Returns:
        Whether the call held a reply that has no fault.
    """
    return row["status"] == STATUS_OK and any(row["flags"])


def case_set(case: dict) -> str:
    """Return the case's set: its ``group`` field when present, else the part of its id before ``/``.

    Args:
        case: The case row.

    Returns:
        The set name.
    """
    return case.get("group") or case["id"].split(CASE_ID_SEPARATOR)[0]


def _new_totals() -> dict:
    return {
        "fault_calls": 0,
        "fault_held": 0,
        STATUS_SHAPE: 0,
        STATUS_ERROR: 0,
        "missing": 0,
        "incident1_list_flags": 0,
        "incident_held": defaultdict(int),
        "walls": [],
        "costs": [],
    }


def _count_call_measures(case: dict, row: dict, totals: dict) -> None:
    if row["status"] in (STATUS_SHAPE, STATUS_ERROR):
        totals[row["status"]] += 1
    if row["status"] in ALL_SCORED_STATUSES and row.get("wall_s") is not None:
        totals["walls"].append(row["wall_s"])
    if row.get("cost_usd") is not None:
        totals["costs"].append(row["cost_usd"])
    if (
        case.get("incident1_row")
        and row["status"] == STATUS_OK
        and row["flags"][LIST_FLAG_INDEX]
    ):
        totals["incident1_list_flags"] += 1


def _count_call_label(case: dict, row: dict, run_counts: dict, totals: dict) -> None:
    label = case["label"]
    if label == PASS_LABEL:
        run_counts["pass"] += 1
        run_counts["wrong"] += int(is_wrong_hold(row))
        return
    if label not in ALL_NEEDED_FLAG_INDEXES:
        return
    run_counts["fault"] += 1
    totals["fault_calls"] += 1
    if is_held(row, label):
        run_counts["held"] += 1
        totals["fault_held"] += 1
        if case["id"] in ALL_INCIDENT_TWIN_IDS:
            totals["incident_held"][case["id"]] += 1


def score(
    all_cases: list[dict], all_stored_rows: list[dict], digest: str, runs: int
) -> dict:
    """Return the counts for the digest, per set and run, and the totals.

    Args:
        all_cases: The case rows.
        all_stored_rows: The rows in the call log.
        digest: The run digest to score.
        runs: How many runs each case had.

    Returns:
        ``sets`` maps set and run to fault, held, pass and wrong counts; ``totals``
        holds the fault calls held, shape, error and missing rows, incident 1 list
        flags, incident twin holds, and each call's wall time and cost.
    """
    rows = latest_rows(all_stored_rows, digest)
    sets: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    totals = _new_totals()
    for each_case, each_run in (
        (case, run) for case in all_cases for run in range(runs)
    ):
        row = rows.get((each_case["id"], each_run))
        if row is None:
            totals["missing"] += 1
            continue
        _count_call_measures(each_case, row, totals)
        _count_call_label(each_case, row, sets[case_set(each_case)][each_run], totals)
    return {
        "sets": {
            name: {run: dict(counts) for run, counts in by_run.items()}
            for name, by_run in sets.items()
        },
        "totals": totals,
    }


def wrong_holds_per_run(scored: dict, all_set_names: list[str], runs: int) -> list[int]:
    """Return the wrong holds in each run, summed over the named sets.

    Args:
        scored: The ``score`` output.
        all_set_names: The sets to sum.
        runs: How many runs to count.

    Returns:
        One count per run.
    """
    return [
        sum(
            scored["sets"].get(each_name, {}).get(each_run, {}).get("wrong", 0)
            for each_name in all_set_names
        )
        for each_run in range(runs)
    ]


def _main_stop_bar(scored: dict, runs: int) -> list[tuple[str, bool]]:
    main_wrong = wrong_holds_per_run(scored, [MAIN_STOP_BARS], runs)
    return [
        (
            f"main stops: wrong holds per run {main_wrong}, bar at most {MAIN_STOP_WRONG_HOLD_BAR}",
            all(each <= MAIN_STOP_WRONG_HOLD_BAR for each in main_wrong),
        )
    ]


def _wrong_hold_bars(scored: dict, runs: int) -> list[tuple[str, bool]]:
    other_sets = [each for each in scored["sets"] if each != SEPARATE_PASS_SET]
    other_wrong = wrong_holds_per_run(scored, other_sets, runs)
    separate_wrong = wrong_holds_per_run(scored, [SEPARATE_PASS_SET], runs)
    return [
        (
            f"pass rows outside {SEPARATE_PASS_SET}: wrong holds per run {other_wrong}, bar at most {OTHER_PASS_WRONG_HOLD_BAR}",
            all(each <= OTHER_PASS_WRONG_HOLD_BAR for each in other_wrong),
        ),
        (
            f"{SEPARATE_PASS_SET} pass rows: wrong holds per run {separate_wrong}, bar at most {SEPARATE_PASS_WRONG_HOLD_BAR}",
            all(each <= SEPARATE_PASS_WRONG_HOLD_BAR for each in separate_wrong),
        ),
    ]


def _fault_bars(scored: dict, runs: int) -> list[tuple[str, bool]]:
    totals = scored["totals"]
    held_share = (
        totals["fault_held"] / totals["fault_calls"] if totals["fault_calls"] else 0.0
    )
    incident_counts = {
        each_id: totals["incident_held"].get(each_id, 0)
        for each_id in ALL_INCIDENT_TWIN_IDS
    }
    return [
        (
            f"fault calls held {totals['fault_held']}/{totals['fault_calls']} = {held_share:.1%}, bar at least {FAULT_HELD_SHARE_BAR:.0%}",
            held_share >= FAULT_HELD_SHARE_BAR,
        ),
        (
            f"incident twins held {incident_counts} of {runs} runs",
            all(each == runs for each in incident_counts.values()),
        ),
        (
            f"list flags on incident 1 rows {totals['incident1_list_flags']}, bar 0",
            totals["incident1_list_flags"] == 0,
        ),
        (f"shape rows {totals[STATUS_SHAPE]}, bar 0", totals[STATUS_SHAPE] == 0),
    ]


def bar_lines(scored: dict, runs: int, bars: str) -> list[tuple[str, bool]]:
    """Return each bar's line and whether it passed.

    Args:
        scored: The ``score`` output.
        runs: How many runs each case had.
        bars: ``eval`` for the cases.json bars, ``main`` for the local main-stop bar.

    Returns:
        One (line, passed) pair per bar.
    """
    if bars == MAIN_STOP_BARS:
        return _main_stop_bar(scored, runs)
    return _fault_bars(scored, runs) + _wrong_hold_bars(scored, runs)


def summary_lines(scored: dict, runs: int) -> list[str]:
    """Return the per-set table, the error and missing counts, and the wall time and cost lines.

    Args:
        scored: The ``score`` output.
        runs: How many runs each case had.

    Returns:
        The lines to print, one set per line, then the totals.
    """
    all_lines = []
    for each_name in sorted(scored["sets"]):
        by_run = scored["sets"][each_name]

        def per_run(field: str) -> list[int]:
            return [by_run.get(each_run, {}).get(field, 0) for each_run in range(runs)]

        all_lines.append(
            f"{each_name}: fault held {per_run('held')} of {per_run('fault')}; wrong holds {per_run('wrong')} of {per_run('pass')}"
        )
    totals = scored["totals"]
    all_lines.append(f"errors {totals[STATUS_ERROR]}, missing {totals['missing']}")
    walls = sorted(totals["walls"])
    if walls:
        ninetieth = walls[int(len(walls) * NINETIETH_PERCENTILE)]
        all_lines.append(
            f"wall per call: median {walls[len(walls) // 2]} s, p90 {ninetieth} s, worst {walls[-1]} s over {len(walls)} calls"
        )
    costs = totals["costs"]
    if costs:
        all_lines.append(
            f"cost per call: mean ${sum(costs) / len(costs):.5f}, total ${sum(costs):.4f}"
        )
    return all_lines
