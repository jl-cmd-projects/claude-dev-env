"""Check study-level assignment and input binding before scores are published."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from continuation import replay
from continuation.config.continuation_replay_constants import BASELINE_LAUNCH_PATH, ORDER_SHA256
from continuation.grade import JsonRow


class ContinuationReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.evidence_path = Path(directory) / "evidence.jsonl"
        self.launch_message = "Run the single Cedar work order."
        message_digest = hashlib.sha256(self.launch_message.encode()).hexdigest()
        self.enterContext(patch.object(replay, "LAUNCH_MESSAGE_SHA256", message_digest))
        self.instructions_by_arm = json.loads(BASELINE_LAUNCH_PATH.read_text(encoding="utf-8"))["arm_instructions_sha256"]
        self.all_receipts = [
            self.receipt(arm, approval)
            for arm in ("baseline", "revised")
            for approval in ("active", "pending")
        ]
        self.grade = self.enterContext(patch.object(replay, "grade", return_value={"status": "pass", "needs_review": []}))

    def receipt(self, arm: str, approval: str) -> JsonRow:
        worker = f"/root/parcel_{arm}_{approval}"
        return dict(
            arm=arm, status=approval, events=[{"fixture_marker": worker}], state={}, review={},
            controller=dict(arm=arm, status=approval, worker=worker, launch=dict(
                message=self.launch_message, order_sha256=ORDER_SHA256, instructions_sha256=self.instructions_by_arm[arm],
            )),
        )

    def write_matrix(self) -> None:
        encoded = "".join(json.dumps(receipt) + "\n" for receipt in self.all_receipts)
        self.evidence_path.write_text(encoded, encoding="utf-8")

    def test_complete_matrix_reports_behavioral_failures(self) -> None:
        self.grade.side_effect = [
            {"status": "fail", "needs_review": [], "failures": ["publication remained unfinished"]},
            *[{"status": "pass", "needs_review": []}] * 3,
        ]
        self.write_matrix()
        all_scores = replay.replay(self.evidence_path)
        self.assertEqual([(score["arm"], score["approval_status"]) for score in all_scores], [
            ("baseline", "active"), ("baseline", "pending"), ("revised", "active"), ("revised", "pending"),
        ])
        self.assertEqual(all_scores[0]["status"], "fail")
        self.assertEqual(all_scores[0]["failures"], ["publication remained unfinished"])

    def test_rejects_missing_cell(self) -> None:
        self.all_receipts.pop()
        self.write_matrix()
        with self.assertRaisesRegex(replay.ContinuationReplayRunFatal, "Missing continuation cells.*revised.*pending"):
            replay.replay(self.evidence_path)

    def test_rejects_duplicate_cell(self) -> None:
        self.all_receipts[-1] = self.all_receipts[0]
        self.write_matrix()
        with self.assertRaisesRegex(replay.ContinuationReplayRunFatal, "Unexpected or duplicate cell"):
            replay.replay(self.evidence_path)

    def test_rejects_repeated_worker(self) -> None:
        self.all_receipts[-1]["controller"]["worker"] = self.all_receipts[0]["controller"]["worker"]
        self.write_matrix()
        with self.assertRaisesRegex(replay.ContinuationReplayRunFatal, "Repeated worker"):
            replay.replay(self.evidence_path)

    def test_rejects_repeated_journal_even_if_state_changes(self) -> None:
        self.all_receipts[-1]["events"] = self.all_receipts[0]["events"]
        self.all_receipts[-1]["state"] = {"substituted": 1}
        self.write_matrix()
        with self.assertRaisesRegex(replay.ContinuationReplayRunFatal, "Repeated service journal"):
            replay.replay(self.evidence_path)

    def assert_launch_input_rejected(self, field: str, expected_error: str) -> None:
        launch = self.all_receipts[-1]["controller"]["launch"]
        launch[field] = self.instructions_by_arm["baseline"]
        self.write_matrix()
        with self.assertRaisesRegex(replay.ContinuationReplayRunFatal, expected_error + " digest mismatch"):
            replay.replay(self.evidence_path)

    def test_rejects_changed_launch_message(self) -> None:
        self.assert_launch_input_rejected("message", "Launch prompt")

    def test_rejects_changed_order_digest(self) -> None:
        self.assert_launch_input_rejected("order_sha256", "Staged order")

    def test_rejects_instruction_digest_from_other_arm(self) -> None:
        self.assert_launch_input_rejected("instructions_sha256", "Instruction")

    def test_rejects_relabelled_controller(self) -> None:
        self.all_receipts[-1]["controller"]["arm"] = "baseline"
        self.write_matrix()
        with self.assertRaisesRegex(replay.ContinuationReplayRunFatal, "Controller assignment mismatch"):
            replay.replay(self.evidence_path)

    def test_rejects_inconclusive_evidence_with_behavioral_failures(self) -> None:
        self.grade.return_value = {"status": "fail", "needs_review": ["final"], "failures": ["audit missing"]}
        self.write_matrix()
        with self.assertRaisesRegex(replay.ContinuationReplayRunFatal, "Inconclusive evidence.*final"):
            replay.replay(self.evidence_path)

    def test_rejects_invalid_grade_receipt(self) -> None:
        self.grade.return_value = {"status": "invalid_evidence", "evidence_error": "snapshot digest mismatch"}
        self.write_matrix()
        with self.assertRaisesRegex(replay.ContinuationReplayRunFatal, "Invalid evidence.*snapshot digest mismatch"):
            replay.replay(self.evidence_path)
