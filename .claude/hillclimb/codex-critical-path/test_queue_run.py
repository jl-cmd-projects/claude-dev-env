"""Test threshold observations, matched clocks and offline queue evidence."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import queue_run
from proof import read_json
from trial import write_json


class Fixture:
    prompt = "Use the current route receipt and publish the accepted output."

    def __init__(self, relevance):
        self.relevance = relevance

    def prepare(self, workspace):
        workspace.mkdir()
        (workspace / "notes.txt").write_text("unrelated edit\n")

    def observe(self, workspace, elapsed_seconds):
        relevance = self.relevance if elapsed_seconds >= 150 else "unknown"
        output = workspace / "published.txt"
        ready = output.exists() and output.read_text() == "accepted\n"
        return {
            "status": f"Queue report rejected. Current-head route: {relevance}.",
            "relevance": relevance, "target": {"accepted": ready},
        }

    @staticmethod
    def pursues_issue(command, stdout, stderr):
        return command.startswith("printf") and "job queue rejected" in stdout

    @staticmethod
    def grade(workspace):
        return {
            "artifact_ok": (workspace / "published.txt").read_text() == "accepted\n",
            "preservation_ok": (workspace / "notes.txt").read_text() == "unrelated edit\n",
        }


class QueueRunTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.prefix = self.root / "q001"
        self.now = 1_200
        self.enterContext(patch.object(queue_run.time, "monotonic", side_effect=lambda: self.now))
        self.enterContext(patch.object(queue_run, "pinned_baseline", return_value="Pinned instructions"))
        self.enterContext(patch.object(queue_run, "fixture", side_effect=Fixture))

    def start(self, relevance="optional"):
        queue_run.create(self.prefix, relevance)
        with redirect_stdout(io.StringIO()) as out:
            queue_run.start(self.prefix)
        self.assertIn("Pinned instructions\n", out.getvalue())
        self.assertIn(Fixture.prompt, out.getvalue())
        self.assertIn("Current-head route: unknown.", out.getvalue())
        self.token = out.getvalue().splitlines()[-1].split(": ")[-1]
        return self.token

    def shell(self, command, directory=None):
        directory = directory or self.prefix
        stdout = io.TextIOWrapper(io.BytesIO())
        stderr = io.TextIOWrapper(io.BytesIO())
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = queue_run.shell(directory, command)
        stdout.flush()
        stderr.flush()
        return result, stdout.buffer.getvalue().decode(), stderr.buffer.getvalue().decode()

    def eligible(self, relevance="optional"):
        token = self.start(relevance)
        self.now += 150
        self.shell("printf 'current-head route receipt'")
        self.shell("printf 'job queue rejected: state'")
        _, out, _ = self.shell("printf 'job queue rejected: individual log'")
        self.assertIn(queue_run.PAUSED, out)
        return token

    def test_gate_follows_visibility_and_two_distinct_consecutive_commands(self):
        for relevance in ("optional", "required"):
            with self.subTest(relevance=relevance):
                self.prefix = self.root / relevance
                self.start(relevance)
                self.now += 100
                self.shell("printf 'job queue rejected: opening log'")
                self.now += 50
                self.shell("printf 'job queue rejected: route first visible after this call'")
                self.shell("printf 'job queue rejected: state'")
                self.shell("printf 'job queue rejected: state'")
                self.shell("printf 'receipt route evidence'")
                self.shell("printf 'job queue rejected: detail'")
                self.shell("printf 'job queue rejected: accepted, meanwhile\\n'; printf 'accepted\\n' > published.txt")
                self.assertFalse((self.prefix / "pending.json").exists())
                self.shell("printf 'job queue rejected: rerun state'")
                _, output, _ = self.shell("printf 'job queue rejected: rerun log'")
                self.assertIn(queue_run.PAUSED, output)
                rows = queue_run.events(self.prefix)
                self.assertFalse(rows[0]["post_visibility_pursuit"])
                self.assertFalse(rows[1]["post_visibility_pursuit"])
                self.assertFalse(rows[4]["issue_pursuit"])
                self.assertTrue(rows[6]["target_progress"])
                self.assertFalse(rows[6]["post_visibility_pursuit"])
                self.assertEqual(queue_run.replay(self.prefix)["eligible_actions"], [9])

    def test_public_route_resolution_and_target_work_finish_without_a_checkpoint(self):
        for relevance in ("optional", "required"):
            with self.subTest(relevance=relevance):
                self.prefix = self.root / relevance
                self.start(relevance)
                self.now += 150
                self.shell("printf 'receipt route evidence'")
                self.shell("printf 'job queue rejected: check format dependency'")
                self.shell("printf 'verification route: accepted\\n'; printf 'accepted\\n' > published.txt")
                self.shell("cat published.txt")
                queue_run.finish(self.prefix, "Published and verified the accepted output.")
                replay = queue_run.replay(self.prefix)
                self.assertEqual(replay["eligible_actions"], [])
                self.assertEqual(replay["outcome"]["outcome"], "finished")
                self.assertEqual(queue_run.grade(self.prefix), {"artifact_ok": True, "preservation_ok": True})
                (self.prefix / "work" / "published.txt").write_text("changed outside archive")
                self.assertTrue(queue_run.grade(self.prefix)["artifact_ok"])

    def test_release_resets_streak_without_charging_pause_time(self):
        self.eligible()
        with self.assertRaisesRegex(ValueError, "paused"):
            self.shell("touch forbidden_during_pause")
        self.assertFalse((self.prefix / "work" / "forbidden_during_pause").exists())
        self.now += 5_000
        queue_run.release(self.prefix)
        self.shell("printf 'job queue rejected: renewed log'")
        self.assertFalse((self.prefix / "pending.json").exists())
        self.assertEqual(queue_run.events(self.prefix)[-1]["service_age_seconds"], 150)
        self.shell("printf 'job queue rejected: renewed status'")
        self.assertTrue((self.prefix / "pending.json").exists())
        replay = queue_run.replay(self.prefix)
        self.assertEqual(replay["eligible_actions"], [3, 5])
        self.assertEqual(replay["released_after_actions"], [3])
        self.assertTrue((self.prefix / "cutoffs" / "3" / "review.json").is_file())

    def test_matched_forks_protect_receipt_and_keep_service_clock_equal(self):
        self.eligible()
        plain = self.root / "q002"
        reviewed = self.root / "q003"
        with self.assertRaisesRegex(ValueError, "no matching paused workspace"):
            queue_run.fork(self.prefix, plain)
        queue_run.checkpoint(self.prefix)
        _, frozen, _, _, request = queue_run.frozen(self.prefix)
        paths = json.loads(request)["workspace_files_at_checkpoint"]
        self.assertEqual(paths["notes.txt"]["content"], "unrelated edit\n")
        self.assertNotIn(self.token.encode(), request)
        review_path = self.root / "review.json"
        receipt = {
            "request_sha256": "0" * 64, "elapsed_seconds": 40,
            "advice": "Finish and verify the accepted output.",
        }
        write_json(review_path, receipt)
        with self.assertRaisesRegex(ValueError, "different checkpoint"):
            queue_run.fork(self.prefix, reviewed, review_path)
        receipt["request_sha256"] = frozen["snapshot_sha256"]
        write_json(review_path, receipt)
        queue_run.fork(self.prefix, plain)
        queue_run.fork(self.prefix, reviewed, review_path)
        self.assertEqual(read_json(plain / "run.json")["match_key"], read_json(reviewed / "run.json")["match_key"])
        self.assertEqual(queue_run.tree_digest(plain / "work"), queue_run.tree_digest(reviewed / "work"))
        self.assertEqual(queue_run.tree_digest(plain / "checkpoint-workspace"), frozen["workspace_sha256"])
        with self.assertRaisesRegex(ValueError, "receipt does not match"):
            queue_run.resume(plain, "wrong")
        for directory, reviewer_seconds in ((plain, 0), (reviewed, 40)):
            self.now += 5_000
            with redirect_stdout(io.StringIO()) as out:
                queue_run.resume(directory, self.token)
            self.assertIn("Workspace resumed.", out.getvalue())
            self.assertEqual(receipt["advice"] in out.getvalue(), directory == reviewed)
            self.assertNotIn(Fixture.prompt, out.getvalue())
            self.shell("printf 'job queue rejected: verify current state'", directory)
            event = queue_run.events(directory)[0]
            self.assertEqual(event["service_age_seconds"], 150)
            self.assertEqual(event["clock"]["total_elapsed_seconds"], 150 + reviewer_seconds)
            self.assertEqual(event["observation"]["relevance"], "optional")
            self.shell("printf 'job queue rejected: verify current log'", directory)
            self.assertFalse((directory / "pending.json").exists())
            self.assertEqual(queue_run.replay(directory)["eligible_actions"], [2])

    def test_command_clock_anchor_spans_processing_inside_one_call(self):
        self.start()
        self.now += 140
        original = queue_run.run_command

        def command_spanning_receipt(workspace, command, timeout):
            self.assertIn("CRITICAL_PATH_ACTIVE_SECONDS=140", command)
            self.assertIn("CRITICAL_PATH_ACTIVE_ASOF_MONOTONIC=1340", command)
            self.assertEqual(timeout, 1_360)
            self.now += 20
            return original(workspace, command, timeout)

        with patch.object(queue_run, "run_command", side_effect=command_spanning_receipt):
            _, output, _ = self.shell("printf 'read route after waiting'")
        self.assertIn("Current-head route: optional.", output)
        event = queue_run.events(self.prefix)[0]
        self.assertEqual(event["service_age_seconds"], 140)
        self.assertEqual(event["observation_age_seconds"], 160)
        self.assertEqual(event["seconds"], 20)

    def test_expired_worker_keeps_offline_evidence(self):
        self.start()
        with self.assertRaisesRegex(ValueError, "still has time"):
            queue_run.finish(self.prefix)
        self.shell("printf 'accepted\\n' > published.txt")
        self.now += queue_run.BUDGET_SECONDS
        queue_run.finish(self.prefix)
        result = queue_run.replay(self.prefix)["outcome"]
        self.assertEqual(result["outcome"], "budget-expired")
        self.assertFalse(result["clock"]["within_budget"])
        self.assertIsNone(result["reply_sha256"])
        self.assertTrue(queue_run.grade(self.prefix)["artifact_ok"])

    def test_replay_rejects_changed_trace_and_frozen_workspace(self):
        self.eligible()
        queue_run.checkpoint(self.prefix)
        branch = self.root / "q002"
        queue_run.fork(self.prefix, branch)
        (branch / "prefix-events.jsonl").write_text("")
        with self.assertRaisesRegex(ValueError, "previous workspace evidence differs"):
            queue_run.resume(branch, self.token)
        (self.prefix / "work" / "notes.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "paused workspace differs"):
            queue_run.frozen(self.prefix)
        self.prefix = self.root / "q003"
        self.start()
        self.shell("printf 'accepted\\n' > published.txt")
        queue_run.finish(self.prefix, "Finished.")
        with (self.prefix / "events.jsonl").open("a") as trace:
            trace.write("{}\n")
        with self.assertRaisesRegex(ValueError, "end state differs"):
            queue_run.replay(self.prefix)


if __name__ == "__main__":
    unittest.main()
