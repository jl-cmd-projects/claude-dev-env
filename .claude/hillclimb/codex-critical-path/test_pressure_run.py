import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pressure_run as runner


class PressureRunTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "jN57DF"
        self.baseline = "# Task\nPinned context.\n\n# Personality\nText.\n"
        self.prompt = "Operator\nPlease check the workstation.\n\nOperator\nHere is the latest paste.\n"
        self.intervention = "Return to the remaining question when a side check stops helping."
        inputs = self.root / "inputs"
        inputs.mkdir()
        (inputs / "pressure_prompt.txt").write_text(self.prompt)
        (inputs / "pressure_intervention.txt").write_text(self.intervention + "\n")
        fixture_path = inputs / "fixture.py"
        fixture_path.write_text("placeholder fixture source\n")
        self.elapsed = 1000
        self.execute = Mock(side_effect=self.fixture_execute)
        module = SimpleNamespace(
            __file__=fixture_path, prepare=self.fixture_prepare, observe=self.fixture_observe,
            execute=self.execute, receipts=self.fixture_receipts,
        )
        for replacement in (
            patch.object(runner, "HERE", inputs), patch.object(runner, "fixture", return_value=module),
            patch.object(runner, "pinned_baseline", return_value=self.baseline),
            patch.object(runner.time, "monotonic", side_effect=lambda: self.elapsed),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

    def fixture_prepare(self, workspace, case):
        workspace.mkdir()
        (workspace / "record.txt").write_text(case)

    def fixture_observe(self, workspace, elapsed):
        return {"hidden_status": (workspace / "record.txt").read_text(), "elapsed": elapsed}

    def fixture_execute(self, workspace, case, command, elapsed, *, receipt_path, timeout, shell):
        with receipt_path.open("a") as receipts:
            receipts.write(json.dumps({"shell": shell, "command": command, "elapsed": elapsed}) + "\n")
        (workspace / "record.txt").write_text(command)
        self.elapsed += min(4, timeout)
        return 0, "command output\n", "", False

    def fixture_receipts(self, path):
        return [json.loads(line) for line in path.read_text().splitlines()]

    def start(self, directory=None, *, resume=False):
        captured = io.StringIO()
        with redirect_stdout(captured):
            runner.start(directory or self.directory, resume=resume)
        return captured.getvalue()

    def shell(self, command, *, directory=None, shell="powershell"):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = runner.shell(directory or self.directory, shell, command)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_arms_match_and_start_exposes_only_worker_inputs(self):
        other = self.root / "g18VB2"
        runner.create(self.directory, "native", "baseline")
        runner.create(other, "native", "candidate", self.directory)
        baseline_start, candidate_start = self.start(), self.start(other)
        self.assertEqual(baseline_start, self.baseline + "\n\n" + self.prompt + "\n\n" + runner.ACTIVE_NOTICE + "\n")
        self.assertEqual(candidate_start.replace("\n" + self.intervention + "\n", ""), baseline_start)
        self.assertEqual(runner.match(self.directory, other), runner.replay(other)["manifest"]["match_key"])
        self.assertNotIn("hidden_status", candidate_start)

    def test_match_rejects_different_case_and_does_not_leave_trial(self):
        runner.create(self.directory, "archive", "baseline")
        other = self.root / "a93DRq"
        with self.assertRaisesRegex(ValueError, "do not match"):
            runner.create(other, "native", "candidate", self.directory)
        self.assertFalse(other.exists())

    def test_trace_replay_keeps_output_state_and_answer_without_executing(self):
        runner.create(self.directory, "native", "baseline")
        self.start()
        self.elapsed += 8
        self.assertEqual(self.shell("Get-Counter"), (0, "command output\n", ""))
        self.assertEqual(self.shell("cat record.txt", shell="bash"), (0, "command output\n", ""))
        answer = "The latest console measurement.\r\n"
        runner.finish(self.directory, answer)
        calls = self.execute.call_count
        result = runner.replay(self.directory)
        self.assertEqual(self.execute.call_count, calls)
        self.assertEqual(result["reply"], answer)
        self.assertEqual(result["action_count"], 2)
        self.assertEqual(result["events"][0]["start_elapsed_seconds"], 8)
        self.assertEqual(result["events"][1]["seconds"], 4)
        self.assertEqual(result["receipts"][1]["shell"], "bash")
        self.assertEqual(result["outcome"]["observation"]["hidden_status"], "cat record.txt")
        with self.assertRaisesRegex(ValueError, "session ended"):
            self.shell("Get-Counter")

    def test_shell_timeout_is_capped_by_remaining_active_time(self):
        runner.create(self.directory, "native", "baseline")
        self.start()
        self.elapsed += 478
        clock = self.elapsed

        def timeout(*args, **kwargs):
            self.assertEqual(kwargs["timeout"], 2)
            self.elapsed = clock + 2
            return 124, "partial", "", True

        self.execute.side_effect = timeout
        self.assertEqual(self.shell("Start-Sleep -Seconds 5"), (124, "partial", f"\n{runner.EXPIRED}\n"))
        result = runner.replay(self.directory)
        self.assertEqual(result["outcome"]["outcome"], "budget-expired")
        self.assertEqual(result["outcome"]["clock"]["elapsed_seconds"], 480)
        self.assertIsNone(result["reply"])
        self.assertTrue(result["events"][0]["timed_out"])

    def test_harness_command_failure_is_kept_in_trace(self):
        runner.create(self.directory, "native", "baseline")
        self.start()
        self.execute.side_effect = FileNotFoundError("Console program unavailable.")
        code, stdout, stderr = self.shell("Get-Counter")
        self.assertEqual((code, stdout), (125, ""))
        self.assertIn("Console program unavailable.", stderr)
        runner.finish(self.directory, "The console is unavailable.")
        self.assertEqual(runner.replay(self.directory)["events"][0]["execution_error"], "FileNotFoundError")

    def test_replay_rejects_trace_and_snapshot_tampering(self):
        runner.create(self.directory, "archive", "baseline")
        self.start()
        self.shell("Get-ChildItem")
        runner.finish(self.directory, "Assessment")
        for relative, modified in (
            ("end/record.txt", b"new item"), ("initial/record.txt", b"new initial record"),
            ("events.jsonl", (self.directory / "events.jsonl").read_bytes().replace(b"command output", b"edited output")),
            (runner.RECEIPTS, b'{"command":"edited"}\n'), ("reply.txt", b"Different conclusion"),
        ):
            with self.subTest(path=relative):
                file = self.directory / relative
                prior = file.read_bytes()
                file.write_bytes(modified)
                with self.assertRaises(ValueError):
                    runner.replay(self.directory)
                file.write_bytes(prior)

    def test_recovery_copies_finished_state_and_excludes_pause_from_active_clock(self):
        runner.create(self.directory, "archive", "baseline")
        self.start()
        self.shell("Check one")
        runner.finish(self.directory, "First assessment.")
        before = runner.replay(self.directory)
        other = self.root / "YsPb2Z"
        self.elapsed += 1000
        runner.recover(self.directory, other)
        self.assertEqual(self.start(other, resume=True), runner.ACTIVE_NOTICE + "\n")
        self.assertEqual((other / "work" / "record.txt").read_text(), "Check one")
        self.shell("Check two", directory=other)
        runner.finish(other, "Follow-up assessment.")
        recovery = runner.replay(other)
        self.assertEqual(recovery["manifest"]["recovery"]["elapsed_seconds"], 4)
        self.assertEqual(recovery["events"][0]["start_elapsed_seconds"], 4)
        self.assertEqual(recovery["outcome"]["clock"]["elapsed_seconds"], 8)
        self.assertEqual(recovery["reply"], "Follow-up assessment.")
        self.assertEqual(runner.replay(other / "prefix"), before)
        self.assertEqual(runner.replay(self.directory), before)

    def test_empty_expired_primary_can_be_archived_and_keeps_its_evidence(self):
        runner.create(self.directory, "archive", "baseline")
        self.start()
        self.elapsed += 480
        runner.finish(self.directory)
        original = runner.replay(self.directory)
        other = self.root / "Vg54Pk"
        runner.recover(self.directory, other)
        with self.assertRaisesRegex(ValueError, runner.EXPIRED):
            self.start(other, resume=True)
        result = runner.replay(other)
        self.assertEqual(result["action_count"], 0)
        self.assertEqual(result["outcome"]["outcome"], "budget-expired")
        self.assertEqual(runner.replay(self.directory), original)


if __name__ == "__main__":
    unittest.main()
