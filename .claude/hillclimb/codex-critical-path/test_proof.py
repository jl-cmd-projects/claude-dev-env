"""Tests for trial evidence capture and oracle replay."""

import json
import tempfile
import unittest
from pathlib import Path

import proof
from continuation import fork
from trial import create, digest, grade, write_json


class ProofTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runs = self.root / "runs"
        self.blind = self.root / "blind"
        self.blind.mkdir()
        self.output = self.root / "proof"
        self.trace_grades = {}

    def complete(self, run_id, trace_grade=None):
        directory = self.runs / run_id
        sentinel = self.root / "recorded-command-executed"
        event = {"command": f"touch {sentinel}", "start": 11, "seconds": 0.25,
                 "exit": 3, "stdout": f"{run_id} output\n", "stderr": "failed\n"}
        trace = json.dumps(event).encode() + b"\n"
        (directory / "events.jsonl").write_bytes(trace)
        (directory / "started").write_text("10")
        (directory / "reply.txt").write_text("Recorded answer.\n")
        clock = {"elapsed_seconds": 4.0, "within_budget": True}
        write_json(directory / "clock.json", clock)
        if trace_grade is not None:
            self.trace_grades[run_id] = trace_grade
            write_json(self.blind / "grading.json", self.trace_grades)
            write_json(self.blind / f"{run_id}.json", {
                "prompt": (directory / "task.txt").read_text(), "events": [event],
                "reply": "Recorded answer.\n", "clock": clock,
                "grade": grade(proof.read_json(directory / "run.json")["case"], directory / "work"),
            })

    def grade_trace(self, **changes):
        return {
            "diversions": [], "repeated_no_progress": [], "verification_ok": True,
            "false_done": False, "missed_dependency": False, "rationale": "Test grade.",
            **changes,
        }

    def test_capture_matches_variants_and_replays_dirty_workspace(self):
        for run_id, arm in (("a", "baseline"), ("b", "candidate")):
            create(self.runs / run_id, "pickup-brief", arm)
            self.complete(run_id, self.grade_trace(diversions=[1], repeated_no_progress=[1]))
        result = proof.capture(self.runs, [self.blind], self.output)
        self.assertEqual(result, proof.replay(self.output))
        self.assertEqual(len(result["match_groups"]), 1)
        match = next(iter(result["match_groups"].values()))
        self.assertTrue(match["matching_variants"])
        self.assertEqual(match["runs_by_arm"], {"baseline": ["a"], "candidate": ["b"]})
        record = proof.read_json(self.output / "a" / "proof.json")
        paths = record["dirty_state"]["paths"]
        draft = paths["operations/shift-notes.md"]
        self.assertNotEqual(draft["pristine_base64"], draft["before_run_base64"])
        self.assertEqual(record["dirty_state"]["end_git_status"], [" M operations/shift-notes.md"])
        self.assertTrue(record["metrics"]["preservation_ok"])
        self.assertFalse(record["metrics"]["verified_oracle_outcome"])
        self.assertEqual(record["metrics"]["diversion_count"], 1)
        self.assertEqual(record["metrics"]["repeated_attempt_count"], 1)
        self.assertEqual(record["metrics"]["diversion_tool_seconds"], 0.25)
        self.assertEqual((self.output / "a" / "events.jsonl").read_bytes(),
                         (self.runs / "a" / "events.jsonl").read_bytes())
        self.assertFalse((self.root / "recorded-command-executed").exists())

    def test_different_task_or_launcher_metadata_does_not_match(self):
        create(self.runs / "a", "published-index", "baseline")
        create(self.runs / "b", "published-index", "candidate", "A changed task")
        create(self.runs / "c", "published-index", "candidate")
        for run_id in ("a", "b", "c"):
            self.complete(run_id, self.grade_trace())
        metadata = {"c": {"model": "gpt-6.2-sol", "effort": "high", "launcher": "hosted"}}
        result = proof.capture(self.runs, [self.blind], self.output, declared=metadata)
        self.assertEqual(len(result["match_groups"]), 3)
        self.assertTrue(all(not group["matching_variants"] for group in result["match_groups"].values()))
        self.assertEqual(result, proof.replay(self.output))

    def test_checkpoint_and_reviewer_are_bound_to_same_task(self):
        prefix = self.runs / "prefix"
        create(prefix, "checkpoint", "baseline")
        (prefix / "work" / "out").mkdir()
        (prefix / "work" / "out" / "daily-deliveries.csv").write_text("checkpoint\n")
        self.complete("prefix")
        branch = self.runs / "a"
        fork(prefix, branch, "csv", "baseline")
        reviewer = self.runs / "reviewer"
        reviewer.mkdir()
        request = (branch / "task.txt").read_bytes()
        (reviewer / "request.txt").write_bytes(request)
        receipt = {"session": "reviewer", "elapsed_seconds": 2.0,
                   "request_sha256": digest(request), "advice": "Check the dispatch ledger."}
        write_json(reviewer / "receipt.json", receipt)
        fork(prefix, self.runs / "b", "csv", "reviewer", reviewer / "receipt.json")
        for run_id in ("a", "b"):
            self.complete(run_id, self.grade_trace(verification_ok=False, false_done=True, missed_dependency=True))
        result = proof.capture(self.runs, [self.blind], self.output)
        self.assertEqual(result, proof.replay(self.output))
        self.assertTrue(next(iter(result["match_groups"].values()))["matching_variants"])
        record = proof.read_json(self.output / "b" / "proof.json")
        self.assertEqual(record["prefix"]["run_id"], "prefix")
        self.assertEqual(record["reviewer"]["receipt"], receipt)
        self.assertEqual(record["metrics"]["total_elapsed_seconds"], 6.0)
        self.assertEqual(record["metrics"]["reviewer_count"], 1)
        self.assertTrue(record["metrics"]["false_done"])
        self.assertTrue(record["metrics"]["missed_dependency"])

    def test_capture_rejects_different_blinded_input_and_replay_rejects_changed_trace(self):
        create(self.runs / "a", "published-index", "baseline")
        self.complete("a", self.grade_trace())
        (self.runs / "a" / "reply.txt").write_text("Different answer.\n")
        with self.assertRaisesRegex(ValueError, "blind grading input differs"):
            proof.capture(self.runs, [self.blind], self.output)
        (self.runs / "a" / "reply.txt").write_text("Recorded answer.\n")
        proof.capture(self.runs, [self.blind], self.output)
        (self.output / "a" / "events.jsonl").write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "trace SHA-256 differs"):
            proof.replay(self.output)

    def test_restore_rejects_path_escape_before_changing_workspace(self):
        workspace = self.root / "work"
        workspace.mkdir()
        sentinel = workspace / "keep"
        sentinel.write_text("keep")
        with self.assertRaisesRegex(ValueError, "unsafe fixture path"):
            proof.restore(workspace, {"../escape": {"content_base64": "", "mode": 0o600}})
        self.assertTrue(sentinel.is_file())
        self.assertFalse((self.root / "escape").exists())


if __name__ == "__main__":
    unittest.main()
