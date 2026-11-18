"""Verify that replay binds each captured session to its intended assignment."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import replay


def _digest(receipt: dict[str, object]) -> str:
    capture = {"events": receipt["events"], "state": receipt["state"]}
    return hashlib.sha256(json.dumps(capture, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.case = "approval-resume"
        self.baseline = self.load_archive("pilot.jsonl", "baseline")
        self.revised = self.load_archive("validation.jsonl", "revised")
        self.order = {
            "worker_by_arm": {"baseline": "order_b1", "revised": "order_b3"},
            "receipt_sha256_by_arm": {"baseline": _digest(self.baseline), "revised": _digest(self.revised)},
        }
        directory = self.enterContext(TemporaryDirectory())
        self.evidence = Path(directory)
        (self.evidence / "semantic-review.json").write_bytes((replay.EVIDENCE / "semantic-review.json").read_bytes())
        for each_filename in ("validation.jsonl", "staged.jsonl"):
            (self.evidence / each_filename).write_text("", encoding="utf-8")
        self.enterContext(patch.object(replay, "EVIDENCE", self.evidence))

    def load_archive(self, filename: str, arm: str) -> dict[str, object]:
        lines = (replay.EVIDENCE / filename).read_text(encoding="utf-8").splitlines()
        return next(receipt for receipt in map(json.loads, lines) if receipt["case"] == self.case and receipt["arm"] == arm)

    def write_archive(self, receipts: list[dict[str, object]]) -> None:
        (self.evidence / "launch.json").write_text(json.dumps({"work_orders": {self.case: self.order}}), encoding="utf-8")
        lines = "".join(json.dumps(each_receipt) + "\n" for each_receipt in receipts)
        (self.evidence / "pilot.jsonl").write_text(lines, encoding="utf-8")

    def test_replays_distinct_bound_captures(self) -> None:
        self.write_archive([self.baseline, self.revised])
        self.assertEqual([score["status"] for score in replay.replay()], ["pass", "pass"])

    def test_rejects_capture_from_another_arm(self) -> None:
        self.write_archive([self.baseline, {**self.baseline, "arm": "revised"}])
        with self.assertRaisesRegex(ValueError, "Receipt hash mismatch.*revised"):
            list(replay.replay())

    def test_rejects_reused_capture_even_with_matching_hashes(self) -> None:
        self.order["receipt_sha256_by_arm"]["revised"] = _digest(self.baseline)
        self.write_archive([self.baseline, {**self.baseline, "arm": "revised"}])
        with self.assertRaisesRegex(ValueError, "Duplicate receipt hash"):
            list(replay.replay())

    def test_rejects_missing_capture_before_emitting_scores(self) -> None:
        self.write_archive([self.baseline])
        with self.assertRaisesRegex(ValueError, "Missing assignments.*revised"):
            next(replay.replay())

    def test_rejects_assignment_without_manifest_digest(self) -> None:
        del self.order["receipt_sha256_by_arm"]["revised"]
        self.write_archive([self.baseline, self.revised])
        with self.assertRaisesRegex(ValueError, "Receipt hashes do not match assignments"):
            list(replay.replay())
