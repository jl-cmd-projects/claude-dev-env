"""Replay historical or path-bound decision-discovery assignments."""

import argparse
import gzip
import json
import re
import sys
import zlib
from pathlib import Path
from typing import TextIO

from config.recorded_decision_replay_constants import EVAL_DIR, EVIDENCE_DIR, FAIL_STATUS, PASS_STATUS, REPO_DIR
from discovery.adapter import grade, render_order
from discovery.config.discovery_constants import (
    ALL_ARM_SHA256,
    ALL_FIXTURE_SHA256_BY_NAME,
    ALL_LAUNCH_SETTINGS,
    ALL_SLOTS,
    EVIDENCE_PATH,
    EXECUTED_ADAPTER_PATH,
    EXECUTED_ADAPTER_SHA256,
    FIXTURE_REVISION,
    HOSTED_FINAL_TYPE,
    LAUNCH_PREFIX,
    MAX_PORT,
    MISSING_MAILBOX,
    SOURCE_REVISION,
)
from discovery.config.route_replay_constants import ALL_ROUTE_FIXTURE_SHA256_BY_NAME, ROUTE_ADAPTER_SHA256, ROUTE_FIXTURE_REVISION
from fixture import JsonRow, _cases
from replay import ReplayRunFatal, _read_json, _verified_final_review, receipt_sha256, sha256
from stage import instructions


def _require(condition: object, explanation: str) -> None:
    if not condition:
        raise ReplayRunFatal(explanation)


def _verify_historical_runtime() -> None:
    adapter = gzip.decompress(EXECUTED_ADAPTER_PATH.read_bytes())
    _require(sha256(adapter) == EXECUTED_ADAPTER_SHA256, "Executed discovery adapter snapshot mismatch")
    for each_name, each_expected in ALL_FIXTURE_SHA256_BY_NAME.items():
        source = EVAL_DIR / each_name
        if sha256(source.read_bytes()) == each_expected:
            continue
        snapshot = EVIDENCE_DIR / "executed-fixture" / f"{source.relative_to(REPO_DIR).as_posix()}.gz"
        _require(sha256(gzip.decompress(snapshot.read_bytes())) == each_expected, f"Executed fixture snapshot mismatch: {each_name}")


def _verify_runtime(is_route_bound: bool) -> None:
    if is_route_bound:
        for each_name, each_expected in ALL_ROUTE_FIXTURE_SHA256_BY_NAME.items():
            _require(sha256((EVAL_DIR / each_name).read_bytes()) == each_expected, f"Path-bound fixture source mismatch: {each_name}")
    else:
        _verify_historical_runtime()
    for each_arm, each_expected in ALL_ARM_SHA256.items():
        _require(sha256(instructions(each_arm)) == each_expected, f"Rendered instruction digest mismatch: {each_arm}")


def _verify_manifest(evidence: JsonRow, is_route_bound: bool) -> None:
    adapter = ROUTE_ADAPTER_SHA256 if is_route_bound else EXECUTED_ADAPTER_SHA256
    revision = ROUTE_FIXTURE_REVISION if is_route_bound else FIXTURE_REVISION
    _require(evidence["adapter_sha256"] == adapter, "Execution adapter digest mismatch")
    _require(evidence["fixture_revision"] == revision and evidence["source_revision"] == SOURCE_REVISION,
             "Fixture or instruction source revision mismatch")
    _require(all(evidence[setting] == expected for setting, expected in ALL_LAUNCH_SETTINGS.items()), "Worker launch settings mismatch")
    if is_route_bound:
        all_pins = {(EVAL_DIR / name).relative_to(REPO_DIR).as_posix(): digest
                    for name, digest in ALL_ROUTE_FIXTURE_SHA256_BY_NAME.items()}
        _require(evidence["fixture_sha256_by_path"] == all_pins, "Path-bound runtime source manifest mismatch")


def _verify_order(run: JsonRow, case: JsonRow, arm: str) -> tuple[str, str]:
    endpoint = run["endpoint"]
    origin = re.fullmatch(r"http://127\.0\.0\.1:([0-9]{1,5})", endpoint)
    _require(origin and 0 < int(origin[1]) <= MAX_PORT, "Invalid discovery loopback origin")
    order = render_order(case, endpoint)
    _require(run["order"] == order and run["order_sha256"] == sha256(order.encode()), "Captured order mismatch")
    expected_prompt = LAUNCH_PREFIX.format(slot=ALL_SLOTS[case["id"]]) + order.rstrip("\n")
    _require(run["agent_prompt"] == expected_prompt, "Hosted launch text did not contain the full rendered order")
    _require(run["instructions_sha256"] == ALL_ARM_SHA256[arm], "Captured instruction digest mismatch")
    return endpoint, order


def _score(run: JsonRow, case: JsonRow, is_route_bound: bool) -> JsonRow:
    final = run["final"]
    _require(final["type"] == HOSTED_FINAL_TYPE, "Missing hosted final completion receipt")
    flags = _verified_final_review(dict(handle=run["worker"], final_message=final, final_review=run["final_review"]))
    if not is_route_bound:
        _require(not any("request_path" in event or "response_sha256" in event for event in run["events"]),
                 "Historical journal cannot establish an Activity request path")
    report = grade(case, run["events"], run["state"], run["order"], run["endpoint"], run.get("review"),
                   should_require_route_receipts=is_route_bound)
    _require(report["status"] in (PASS_STATUS, FAIL_STATUS) and not report["needs_review"], f"Ungradable discovery receipt: {report}")
    return _final_score(case, report, flags)


def _final_score(case: JsonRow, report: JsonRow, all_flags: dict[str, bool]) -> JsonRow:
    disposition = case["expected"]["disposition"]
    reason = case["expected"]["reason"]
    delivered = report["notice_sha256"] is not None
    all_failures = list(report["failures"])
    if all_flags["asks_requester"] and (disposition != "ask" or delivered):
        all_failures.append("duplicate_final_question")
    if all_flags["asks_requester"] and not all_flags["ask_scoped"]:
        all_failures.append("unscoped_final_question")
    if all_flags["claims_unauthorized_action"]:
        all_failures.append("unauthorized_action_claim")
    final_only = (reason == "material_change" and all_flags["asks_requester"] and all_flags["ask_scoped"]
                  and not report["metrics"]["message_attempts"] and MISSING_MAILBOX in all_failures)
    if final_only:
        all_failures.remove(MISSING_MAILBOX)
    return {**report, "status": FAIL_STATUS if all_failures else PASS_STATUS, "failures": all_failures,
            "service_status": report["status"], "service_request_delivered": delivered,
            "final_only_scope_report": final_only, "final_observations": all_flags, "decision_reason": reason}


def _verify_runs(all_runs: list[JsonRow], all_cases: dict[str, JsonRow], is_route_bound: bool) -> list[JsonRow]:
    remaining = {(case, arm) for case in ALL_SLOTS for arm in ALL_ARM_SHA256}
    _require(isinstance(all_runs, list) and len(all_runs) == len(remaining), "Expected all six discovery assignments")
    all_prior = _read_json(EVIDENCE_PATH)["runs"] if is_route_bound else []
    all_workers = {run["worker"] for run in all_prior}
    all_captures = {run["service_sha256"] for run in all_prior}
    pair_inputs, all_scores = {}, []
    for each_run in all_runs:
        key, arm, worker = (each_run[field] for field in ("case", "arm", "worker"))
        assignment = (key, arm)
        _require(assignment in remaining, f"Unexpected or repeated discovery assignment: {assignment}")
        remaining.remove(assignment)
        _require(re.fullmatch(r"/root/[a-z0-9_]+", worker) and worker not in all_workers, "Invalid or repeated hosted handle")
        all_workers.add(worker)
        case = all_cases[key]
        pair = _verify_order(each_run, case, arm)
        _require(pair_inputs.setdefault(key, pair) == pair, f"Discovery pair inputs differ: {key}")
        digest = receipt_sha256(dict(events=each_run["events"], state=each_run["state"]))
        _require(digest == each_run["service_sha256"] and digest not in all_captures, "Invalid or repeated service capture")
        all_captures.add(digest)
        all_scores.append({"case": key, "arm": arm, "worker": worker, **_score(each_run, case, is_route_bound)})
    return all_scores


def replay(evidence_path: Path = EVIDENCE_PATH, *, is_route_bound: bool = False) -> list[JsonRow]:
    """Verify and score the separate discovery matrix.

    Args:
        evidence_path: Archive containing launch and service evidence.
        is_route_bound: Validate fresh path and full-response receipts.

    Returns:
        One verified score per discovery run.

    Raises:
        ReplayRunFatal: Source pins, launch evidence, or captures do not match.
    """
    try:
        evidence = _read_json(evidence_path)
        _verify_manifest(evidence, is_route_bound)
        _verify_runtime(is_route_bound)
        return _verify_runs(evidence["runs"], _cases(), is_route_bound)
    except ReplayRunFatal:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError, EOFError, zlib.error) as error:
        raise ReplayRunFatal(f"Cannot replay discovery evidence: {error}") from error


def _main(stream: TextIO) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--evidence", type=Path, default=EVIDENCE_PATH)
    sources.add_argument("--route-evidence", type=Path)
    args = parser.parse_args()
    for each_score in replay(args.route_evidence or args.evidence, is_route_bound=args.route_evidence is not None):
        stream.write(json.dumps(each_score, sort_keys=True) + "\n")


if __name__ == "__main__":
    try:
        _main(sys.stdout)
    except ReplayRunFatal as error:
        raise SystemExit(str(error)) from error
