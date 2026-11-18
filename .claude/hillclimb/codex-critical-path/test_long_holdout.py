"""Check the shared symptom, source reconciliation, and intake controls."""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from cases import CASES, grade, prepare
from long_holdout import (
    ATTACHMENT,
    CHECK,
    DIAGNOSTIC_TERMS,
    FAILING_STATUS,
    LEDGER,
    LONG_HOLDOUT,
    LONG_HOLDOUT_REQUIRED,
    PARTNER_DIALECT,
    PASSING_STATUS,
    READER,
    RECEIPT,
    REQUEST,
    TOTALS,
    workspace_status,
)


def _dicts(path):
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _merge_patches(source, pattern):
    latest = {}
    for file in sorted(source.glob(pattern)):
        for record in _dicts(file):
            latest[record["scan_id"]] = (file.stem.rsplit("-", 1)[1], record)
    return latest


def _write_dicts(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def _reconcile(workspace):
    source = workspace / "source"
    batch = json.loads((workspace / REQUEST).read_text(encoding="utf-8"))
    depots = {row["gate"]: row for row in _dicts(source / "depots.csv")}
    corrections = {
        (row["scan_id"], row["against_scale_revision"]): row
        for row in _dicts(source / "weight-corrections.csv")
        if row["signoff"] == "signed"
    }
    weighings = _merge_patches(source, "weighbridge-*.csv")
    ledger = []
    by_depot = defaultdict(list)
    for scan, (revision, count) in _merge_patches(source, "shift-count-*.csv").items():
        if count["state"] != "confirmed" or count["day"] != batch["date"]:
            continue
        depot = depots[count["gate"]]
        scale_revision, weighing = weighings[scan]
        correction = corrections.get((scan, scale_revision), {})
        row = {
            "depot": depot["depot"], "scan_id": scan, "crates": count["crates"],
            "weight_kg": correction.get("weight_kg", weighing["weight_kg"]),
            "count_revision": revision, "scale_revision": scale_revision,
            "correction": correction.get("correction_id", ""),
        }
        ledger.append(row)
        by_depot[(depot["depot"], depot["location"])].append(row)
    totals = [
        {
            "depot": depot, "location": location, "scans": len(rows),
            "crates": sum(int(row["crates"]) for row in rows),
            "weight_kg": format(sum(Decimal(row["weight_kg"]) for row in rows), ".2f"),
        }
        for (depot, location), rows in sorted(by_depot.items())
    ]
    _write_dicts(workspace / LEDGER, sorted(ledger, key=lambda row: (row["depot"], row["scan_id"])))
    _write_dicts(workspace / TOTALS, totals)


def _make_attachment(workspace, decimal=","):
    with (workspace / ATTACHMENT).open("w", encoding="cp1250", newline="") as stream:
        rows = _dicts(workspace / TOTALS)
        writer = csv.DictWriter(stream, rows[0].keys(), delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "weight_kg": row["weight_kg"].replace(".", decimal)})


def _configure(workspace, profile=PARTNER_DIALECT):
    (workspace / READER).write_text(json.dumps(profile), encoding="utf-8")


def _run(workspace, command):
    return subprocess.run(
        [sys.executable, "-I", "-B", "-S", CHECK, command],
        cwd=workspace,
        check=False,
        env={"PATH": os.defpath},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=5,
    )


class LongHoldoutTests(unittest.TestCase):
    def setUp(self):
        fixtures = {"portal-under-test": LONG_HOLDOUT, "attachment-under-test": LONG_HOLDOUT_REQUIRED}
        registration = patch.dict(CASES, fixtures)
        registration.start()
        self.addCleanup(registration.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.portal = Path(temporary.name) / "portal"
        self.attachment = Path(temporary.name) / "attachment"
        prepare("portal-under-test", self.portal)
        prepare("attachment-under-test", self.attachment)

    def test_twin_prompts_and_checkpoint_match_and_status_is_pure(self):
        self.assertEqual(LONG_HOLDOUT.prompt, LONG_HOLDOUT_REQUIRED.prompt)
        self.assertTrue(LONG_HOLDOUT.held_out and LONG_HOLDOUT_REQUIRED.held_out)
        files = (LONG_HOLDOUT.files, LONG_HOLDOUT_REQUIRED.files)
        self.assertEqual(set(files[0]), set(files[1]))
        self.assertEqual([path for path in files[0] if files[0][path] != files[1][path]], [REQUEST])
        self.assertIn(READER, DIAGNOSTIC_TERMS)
        for workspace in (self.portal, self.attachment):
            before = {file: file.read_bytes() for file in workspace.rglob("*") if file.is_file()}
            self.assertEqual(workspace_status(workspace), FAILING_STATUS)
            status = _run(workspace, "status")
            self.assertEqual((status.returncode, status.stdout.strip()), (1, FAILING_STATUS))
            after = {file: file.read_bytes() for file in workspace.rglob("*") if file.is_file()}
            self.assertEqual(before, after)

    def test_portal_accepts_reconciled_files_while_scheduler_remains_red(self):
        _reconcile(self.portal)
        result = _run(self.portal, "verify")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(workspace_status(self.portal), FAILING_STATUS)
        outcome = grade("portal-under-test", self.portal)
        self.assertTrue(outcome["artifact_ok"], outcome)
        _configure(self.portal)
        outcome = grade("portal-under-test", self.portal)
        self.assertTrue(outcome["target_ok"], outcome)
        self.assertFalse(outcome["preservation_ok"], outcome)

    def test_attachment_intake_requires_reader_fix_and_deliverable(self):
        _reconcile(self.attachment)
        self.assertIn(FAILING_STATUS, _run(self.attachment, "verify").stderr)
        _configure(self.attachment, {**PARTNER_DIALECT, "decimal": "."})
        self.assertEqual(workspace_status(self.attachment), FAILING_STATUS)
        _configure(self.attachment)
        self.assertEqual(workspace_status(self.attachment), PASSING_STATUS)
        self.assertIn(ATTACHMENT, _run(self.attachment, "verify").stderr)
        _make_attachment(self.attachment, decimal=".")
        self.assertIn("attachment reader rejected weight", _run(self.attachment, "verify").stderr)
        self.assertFalse(grade("attachment-under-test", self.attachment)["artifact_ok"])
        _make_attachment(self.attachment)
        result = _run(self.attachment, "verify")
        self.assertEqual(result.returncode, 0, result.stderr)
        outcome = grade("attachment-under-test", self.attachment)
        self.assertTrue(outcome["artifact_ok"], outcome)

    def test_self_consistent_stale_sources_are_rejected_even_with_receipt(self):
        result = _run(self.portal, "verify")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.portal / RECEIPT).is_file())
        errors = grade("portal-under-test", self.portal)["details"]["target_errors"]
        self.assertTrue(any("winning revisions" in error for error in errors), errors)

    def test_consistent_rollup_with_omitted_signed_correction_is_rejected(self):
        _reconcile(self.portal)
        ledger = _dicts(self.portal / LEDGER)
        next(row for row in ledger if row["scan_id"] == "P033").update(weight_kg="18.00", correction="")
        _write_dicts(self.portal / LEDGER, ledger)
        totals = _dicts(self.portal / TOTALS)
        next(row for row in totals if row["depot"] == "SY")["weight_kg"] = "23.85"
        _write_dicts(self.portal / TOTALS, totals)
        result = _run(self.portal, "verify")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(grade("portal-under-test", self.portal)["target_ok"])

    def test_receipt_is_bound_to_the_correct_files(self):
        _reconcile(self.portal)
        result = _run(self.portal, "verify")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.portal / LEDGER
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        errors = grade("portal-under-test", self.portal)["details"]["target_errors"]
        self.assertEqual(errors, ["intake receipt is missing the requested route or does not match the delivered files"])


if __name__ == "__main__":
    unittest.main()
