"""Reconstruct the two installed-handler waves and their blinded closeout inputs."""

import hashlib
import importlib
import json
import subprocess
import sys
from collections import Counter
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests.behavior.scope_drift import suite

with pytest.MonkeyPatch.context() as import_context:
    import_context.setitem(sys.modules, "suite", suite)
    recall = importlib.import_module("tests.behavior.scope_drift.recall_driver")
    apply_changes = importlib.import_module("tests.behavior.scope_drift.replay").apply_captured_changes


def check_wave(source: Path, cases: dict) -> tuple[dict, list]:
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    expected = set(product(("seaport", "estuary", "copper"), ("baseline", "candidate")))
    if len(rows) != len(expected) or {(row["case"], row["arm"]) for row in rows} != expected:
        raise ValueError("Missing or repeated arm and case pair")
    totals = Counter()
    for row in rows:
        case, arm = cases[row["case"]], row["arm"]
        with TemporaryDirectory() as scratch:
            work = Path(scratch) / "work"
            suite.prepare(case, "baseline", work)
            apply_changes(work, row["changed_files"])
            grade = suite.assess(case, "baseline", work)
            hashes = {artifact_path.relative_to(work).as_posix(): suite.digest(artifact_path.read_bytes())
                      for artifact_path in work.rglob("*") if artifact_path.is_file()}
        if hashes != row["final_state_sha256"] or any(
            grade[key] != row[key] for key in ("missing_or_wrong", "unexpected")
        ) or row["files_pass"] != grade["file_checks_pass"]:
            raise ValueError("Reconstructed files or oracle grade differ")
        if (suite.digest(recall._transcript_bytes(case["original"])) != row["transcript_sha256"]
                or suite.digest(case["summary"].encode()) != row["summary_sha256"]
                or hashes["AGENTS.md"] != row["instructions_sha256"]):
            raise ValueError("Initial source fingerprint differs")
        blind = {"id": row["trial"], "task_oracle": case["report"], "final": row["closeout"],
                 "file_mismatches": grade["missing_or_wrong"], "unexpected_changes": grade["unexpected"]}
        if hashlib.sha256(json.dumps(blind, sort_keys=True).encode()).hexdigest() != row["review_packet_entry_sha256"]:
            raise ValueError("The review packet differs from the captured closeout or oracle")
        if row["history_opened"] != (row["transcript_open_events"] > 0):
            raise ValueError("Source-open count differs from the recorded observation")
        for metric, count in (("attempts", 1), ("files", grade["file_checks_pass"]),
                              ("closeouts", row["blind_review"]["report_pass"]), ("source_opens", row["history_opened"])):
            totals[f"{arm}/{metric}"] += int(count)
    return {name: totals[name] for name in sorted(totals)}, rows


def test_installed_waves_reproduce_their_destinations_and_review_inputs() -> None:
    known = subprocess.run(["git", "cat-file", "-e", f"{suite.BASELINE}^{{commit}}"], cwd=suite.ROOT, capture_output=True)
    if known.returncode and subprocess.check_output(["git", "rev-parse", "--is-shallow-repository"], cwd=suite.ROOT).strip() == b"true":
        pytest.skip("The pinned benchmark revision is outside this shallow checkout")
    known.check_returncode()
    cases = {case["id"]: case for case in json.loads((suite.ROOT / "recall.json").read_text())}
    folder = suite.ROOT / "installed"
    compatibility = json.loads((folder / "compatibility.json").read_text())
    workers = set()
    orders = set()
    for filename in ("first.jsonl", "literal-reader.jsonl"):
        scores, rows = check_wave(folder / filename, cases)
        assert scores["baseline/files"] == scores["baseline/closeouts"] == 1
        assert scores["candidate/files"] == scores["candidate/closeouts"] == 3
        assert len(rows) == 6
        for row in rows:
            assert row["trial"] not in orders and row["worker"] not in workers
            orders.add(row["trial"])
            workers.add(row["worker"])
            compared = compatibility["inputs"][row["trial"]]
            assert compared["hook_context_sha256"] == row["hook_output_sha256"]
            assert compared["startup_sha256"] == row["startup_sha256"]
        assert sum(row["files_pass"] and row["blind_review"]["report_pass"] for row in rows if row["arm"] == "baseline") == 1
        assert sum(row["files_pass"] and row["blind_review"]["report_pass"] for row in rows if row["arm"] == "candidate") == 3
