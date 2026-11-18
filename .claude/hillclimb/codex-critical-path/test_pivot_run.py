"""Check visible review eligibility and checkpoint-bound advice."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pivot_run
from long_run import workspace_tree
from proof import read_json
from trial import digest, write_json


class PivotRunTest(unittest.TestCase):
    def setUp(self):
        scratch = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(scratch)
        self.enterContext(patch.object(pivot_run.time, "monotonic", return_value=12.0))

    def prefix(self, name, update="Publish the export and verify it.\n", mode="operator-update"):
        directory = self.root / name
        work = directory / "work"
        work.mkdir(parents=True)
        (work / "status.log").write_text("Build result is pending.\n")
        (work / "export.csv").write_text("number,total\n1,350\n")
        (directory / "instructions.md").write_text("Workspace fixture.\n")
        (directory / "task.txt").write_text("Prepare the task handoff.\n")
        (directory / "operator-update.txt").write_text(update)
        (directory / "events.jsonl").touch()
        write_json(directory / "initial-workspace.json", workspace_tree(work))
        manifest = {
            "case": "bound", "phase": "prefix", "mode": mode, "budget_seconds": 360,
            "input_sha256": pivot_run.hash_files(directory, pivot_run.INPUT_FILES),
        }
        write_json(directory / "run.json", manifest)
        with redirect_stdout(io.StringIO()):
            pivot_run.start(directory, manifest)
        return directory, manifest

    def event(self, action=1, changes=None, artifact_changes=()):
        return {
            "action": action, "command": "cat status.log", "exit": 0,
            "stdout": "Build result is pending.\n", "stderr": "",
            "changes": changes or {}, "artifact_changes": list(artifact_changes),
        }

    def continuation(self, name, update="Publish the export and verify it.\n"):
        prefix, manifest = self.prefix(name, update)
        (prefix / "events.jsonl").write_text(json.dumps(self.event()) + "\n")
        pivot_run.freeze(prefix, manifest, "attempted-finish", 12.0, "I will keep investigating.")
        branch = self.root / f"{name}-branch"
        pivot_run.branch(prefix, manifest, branch)
        return branch, read_json(branch / "run.json")

    def reject(self, directory, manifest, error):
        with redirect_stdout(io.StringIO()) as output, self.assertRaisesRegex(ValueError, error):
            pivot_run.resume(directory, manifest)
        self.assertEqual(output.getvalue(), "")
        self.assertFalse((directory / "started.json").exists())

    def review(self, directory, **receipt):
        write_json(directory / "review.json", {"elapsed_seconds": 2.5, **receipt})
        (directory / "advice.txt").write_text("Verify that the export was handed off.\n")

    def test_eligibility_does_not_use_expected_bytes_or_paths(self):
        for mode, update in (("steady", ""), ("operator-update", "Finish the handoff.\n")):
            with self.subTest(mode=mode):
                directory, manifest = self.prefix(mode, update=update, mode=mode)
                tree = workspace_tree(directory / "work")
                events = [self.event(1), self.event(2)]
                observations = []
                for expected in (("export.csv",), ("different-output.csv",)):
                    for oracle_pass in (False, True):
                        with patch.object(pivot_run, "artifact_paths", return_value=expected) as paths, \
                                patch.object(pivot_run, "artifact_grade", return_value={"pass": oracle_pass}) as oracle:
                            observations.append(pivot_run.review_trigger(directory, manifest, events, tree))
                        paths.assert_not_called()
                        oracle.assert_not_called()
                self.assertTrue(observations[0]["eligible"])
                self.assertTrue(all(row == observations[0] for row in observations))

    def test_eligibility_does_not_use_grader_event_annotations(self):
        directory, manifest = self.prefix("visible-log")
        tree = workspace_tree(directory / "work")
        log_delta = {"status.log": {"before": None, "after": tree["status.log"]}}
        unscored = [self.event(changes=log_delta)]
        scored = [self.event(changes=log_delta, artifact_changes=("status.log",))]
        result = pivot_run.review_trigger(directory, manifest, unscored, tree)
        self.assertTrue(result["eligible"])
        self.assertEqual(result, pivot_run.review_trigger(directory, manifest, scored, tree))
        clean = self.event(changes=log_delta)
        clean["stdout"] = "Build result is available.\n"
        self.assertFalse(pivot_run.review_trigger(directory, manifest, [clean], tree)["eligible"])

    def test_rejects_missing_or_wrong_checkpoint_digest_before_start(self):
        for name, receipt in (("missing", {}), ("wrong", {"request_sha256": "1" * 64})):
            with self.subTest(name=name):
                directory, manifest = self.continuation(name)
                self.review(directory, **receipt)
                self.reject(directory, manifest, "lacks the matching checkpoint digest")

    def test_rejects_receipt_from_a_different_prefix(self):
        first, _ = self.continuation("export")
        other, manifest = self.continuation("profile", "Publish the CI profile and verify it.\n")
        previous_digest = digest((first / "review-input.json").read_bytes())
        self.review(other, request_sha256=previous_digest)
        self.reject(other, manifest, "lacks the matching checkpoint digest")

    def test_rejects_changed_checkpoint_input_even_with_original_receipt(self):
        directory, manifest = self.continuation("stale")
        snapshot = directory / "review-input.json"
        self.review(directory, request_sha256=digest(snapshot.read_bytes()))
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
        self.reject(directory, manifest, "differs from the frozen checkpoint")

    def test_rejects_archival_policy_for_live_review(self):
        directory, manifest = self.continuation("archival")
        checkpoint_file = directory / "prefix-checkpoint.json"
        checkpoint = read_json(checkpoint_file)
        checkpoint.pop("review_policy")
        write_json(checkpoint_file, checkpoint)
        manifest["prefix_checkpoint_sha256"] = digest(checkpoint_file.read_bytes())
        write_json(directory / "run.json", manifest)
        self.review(directory, request_sha256=checkpoint["review_input_sha256"])
        self.reject(directory, manifest, "does not use the visible review policy")

    def test_accepts_matching_receipt_and_records_consumed_bytes(self):
        directory, manifest = self.continuation("matching")
        self.review(directory, request_sha256=digest((directory / "review-input.json").read_bytes()))
        with redirect_stdout(io.StringIO()) as output:
            pivot_run.resume(directory, manifest)
        started = read_json(directory / "started.json")
        self.assertIn("[Independent review]\nVerify that the export was handed off.", output.getvalue())
        self.assertEqual(started["reviewer_seconds"], 2.5)
        self.assertEqual(started["receipt_sha256"], digest((directory / "review.json").read_bytes()))
        self.assertEqual(started["advice_sha256"], digest((directory / "advice.txt").read_bytes()))


if __name__ == "__main__":
    unittest.main()
