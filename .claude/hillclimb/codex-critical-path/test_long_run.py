"""Check the checkpoint, resume, and evidence interface with miniature fixtures."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import long_run
from cases import Case
from proof import read_json
from trial import CASES, digest, write_json


def oracle(workspace):
    return [] if (workspace / "out.txt").read_text() == "ready\n" else ["out.txt is unfinished"]


def workspace_status(workspace):
    return (workspace / "status.txt").read_text().strip()


class LongRunTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prefix = self.root / "t01"
        self.case = Case(
            prompt="Build out.txt and verify its contents.",
            allowed_paths=("out.txt",),
            distraction_paths=("diagnostic.log",),
            verification_commands=("cat out.txt",),
            files={"diagnostic.log": "diagnostic\n", "status.txt": "Status output\n", "draft.txt": "User edit\n"},
            dirty_originals={"draft.txt": "Pristine version\n"},
            check=oracle,
        )
        module = SimpleNamespace(
            LONG_DEV=self.case, LONG_DEV_REQUIRED=replace(self.case, allowed_paths=("out.txt", "diagnostic.log")),
            DIAGNOSTIC_TERMS=("diagnostic.log",), workspace_status=workspace_status,
        )
        self.enterContext(patch.dict(sys.modules, {"long_dev": module}))
        self.enterContext(patch.dict(CASES))
        self.enterContext(patch.object(long_run, "pinned_baseline", return_value="Pinned test instructions"))

    def cli(self, directory, action, *args):
        stdout = io.TextIOWrapper(io.BytesIO())
        stderr = io.TextIOWrapper(io.BytesIO())
        with redirect_stdout(stdout), redirect_stderr(stderr), patch.object(sys, "argv", [
            "long_run.py", str(directory), action, *(str(arg) for arg in args),
        ]):
            try:
                code = long_run.main()
            except SystemExit as exit:
                code = exit.code
        stdout.flush()
        stderr.flush()
        return code, stdout.buffer.getvalue(), stderr.buffer.getvalue()

    def start(self, case="dev-a"):
        self.assertEqual(self.cli(self.prefix, "create", case), (0, b"", b""))
        code, out, error = self.cli(self.prefix, "start")
        self.assertEqual((code, error), (0, b""))
        self.assertIn(self.case.prompt.encode(), out)
        self.assertIn(b"Pinned test instructions", out)
        self.assertIn(b"Status output", out)
        return out.splitlines()[-1].decode().split(": ")[1]

    def freeze_with_diagnostics(self):
        token = self.start()
        self.assertEqual(self.cli(self.prefix, "shell", "ls")[0], 0)
        code, stdout, stderr = self.cli(self.prefix, "shell", "cat diagnostic.log")
        self.assertEqual((code, stderr), (0, b""))
        self.assertIn(b"Status output", stdout)
        self.assertNotIn(b"CHECKPOINT", stdout)
        code, stdout, stderr = self.cli(self.prefix, "shell", "wc -l diagnostic.log; exit 7")
        self.assertEqual((code, stderr), (7, b""))
        self.assertIn(long_run.CHECKPOINT_SENTINEL.encode(), stdout)
        return token

    def test_diagnostic_checkpoint_excludes_longer_trace_and_receipt(self):
        token = self.freeze_with_diagnostics()
        fields = read_json(self.prefix / "checkpoint.json")
        self.assertEqual(fields["reason"], "two-diagnostic-actions")
        self.assertEqual(fields["diagnostic_actions"], [2, 3])
        self.assertEqual(fields["status_observations"], 4)
        self.assertEqual(fields["status_at_cutoff"], "Status output")
        code, stdout, stderr = self.cli(self.prefix, "shell", "touch too-late")
        self.assertEqual((code, stdout), (1, b""))
        self.assertIn(long_run.CHECKPOINT_SENTINEL.encode(), stderr)
        self.assertFalse((self.prefix / "work" / "too-late").exists())
        code, snapshot, stderr = self.cli(self.prefix, "snapshot")
        self.assertEqual((code, stderr), (0, b""))
        decoded = json.loads(snapshot)
        self.assertEqual(decoded["original_user_task"], self.case.prompt)
        self.assertEqual(len(decoded["observed_shell_actions"]), 3)
        self.assertEqual(decoded["workspace_files_at_checkpoint"]["draft.txt"]["content"], "User edit\n")
        self.assertNotIn(token.encode(), snapshot)
        self.assertNotIn(b"too-late", snapshot)
        self.assertEqual(fields["snapshot_sha256"], digest(snapshot))

    def test_checkpoint_checks_first_artifact_change_and_sixth_action(self):
        self.start()
        self.cli(self.prefix, "shell", "echo ready > out.txt")
        first = read_json(self.prefix / "checkpoint.json")
        self.assertEqual(first["reason"], "allowed-artifact-change")
        self.assertEqual(first["status_observations"], 2)
        self.assertEqual(first["changed_allowed_paths"], ["out.txt"])
        self.prefix = self.root / "t02"
        self.start()
        for index in range(6):
            _, out, _ = self.cli(self.prefix, "shell", "ls")
            self.assertEqual(b"CHECKPOINT" in out, index == 5)
        self.assertEqual(read_json(self.prefix / "checkpoint.json")["reason"], "sixth-shell-action")

    def test_branch_preserves_exact_state_and_binds_optional_review(self):
        token = self.freeze_with_diagnostics()
        receipt = self.root / "receipt.json"
        blank = self.root / "c032"
        advised = self.root / "c017"
        review = {
            "session": "short", "request_sha256": "0" * 64,
            "advice": "Write out.txt and validate the result.", "elapsed_seconds": 3.25,
        }
        write_json(receipt, review)
        self.assertEqual(self.cli(self.prefix, "branch", advised, "--review", receipt)[0], 1)
        self.assertFalse(advised.exists())
        review["request_sha256"] = read_json(self.prefix / "checkpoint.json")["snapshot_sha256"]
        write_json(receipt, review)
        self.assertEqual(self.cli(self.prefix, "branch", advised, "--review", receipt)[0], 0)
        self.assertEqual(self.cli(self.prefix, "branch", blank)[0], 0)
        self.assertEqual(read_json(blank / "run.json")["match_key"], read_json(advised / "run.json")["match_key"])
        self.assertEqual(long_run.workspace_tree(blank / "work"), long_run.workspace_tree(advised / "work"))
        self.assertEqual((blank / "prefix-events.jsonl").read_bytes(), (self.prefix / "events.jsonl").read_bytes())
        self.assertEqual(self.cli(blank, "start")[0], 1)
        self.assertEqual(self.cli(blank, "resume", "wrong-receipt")[0], 1)
        self.assertFalse((blank / "started.json").exists())
        self.assertEqual(self.cli(blank, "resume", token), (0, b"Continuation accepted.\n", b""))
        code, output, error = self.cli(advised, "resume", token)
        self.assertEqual((code, error), (0, b""))
        self.assertIn(review["advice"].encode(), output)
        self.assertNotIn(self.case.prompt.encode(), output)
        self.assertEqual(self.cli(advised, "resume", token)[0], 1)
        for branch in blank, advised:
            self.assertEqual(self.cli(branch, "shell", "echo ready > out.txt")[0], 0)
            self.assertEqual(self.cli(branch, "shell", "cat out.txt")[0], 0)
            self.assertEqual(self.cli(branch, "finish", "The output was verified.")[0], 0)
            self.assertEqual(self.cli(branch, "shell", "echo unverified > out.txt")[0], 1)
            self.assertTrue(json.loads(self.cli(branch, "grade")[1])["artifact_ok"])
        self.assertFalse((self.prefix / "work" / "out.txt").exists())
        clock = read_json(advised / "clock.json")
        self.assertEqual(clock["reviewer_seconds"], review["elapsed_seconds"])
        self.assertAlmostEqual(clock["total_elapsed_seconds"], clock["worker_elapsed_seconds"] + 3.25)
        self.assertEqual(read_json(blank / "clock.json")["reviewer_seconds"], 0)

    def test_budget_charges_active_time_and_preserves_timeout_evidence(self):
        with patch.object(long_run, "BUDGET_SECONDS", 1):
            token = self.freeze_with_diagnostics()
        advised = self.root / "k001"
        receipt = self.root / "receipt.json"
        write_json(receipt, {
            "session": "slow", "request_sha256": read_json(self.prefix / "checkpoint.json")["snapshot_sha256"],
            "advice": "Continue.", "elapsed_seconds": 3,
        })
        self.assertEqual(self.cli(self.prefix, "branch", advised, "--review", receipt)[0], 0)
        self.assertEqual(self.cli(advised, "resume", token)[0], 1)
        self.assertFalse(read_json(advised / "budget-expired.json")["within_budget"])
        plain = self.root / "k002"
        self.assertEqual(self.cli(self.prefix, "branch", plain)[0], 0)
        self.assertEqual(self.cli(plain, "resume", token)[0], 0)
        code, output, _ = self.cli(plain, "shell", "echo started; sleep 10; touch after-timeout")
        self.assertEqual(code, 124)
        self.assertIn(b"started", output)
        event = json.loads((plain / "events.jsonl").read_text())
        self.assertTrue(event["timed_out"])
        self.assertFalse(read_json(plain / "budget-expired.json")["within_budget"])
        self.assertFalse((plain / "work" / "after-timeout").exists())

    def test_out_of_band_checkpoint_changes_rejected(self):
        token = self.freeze_with_diagnostics()
        branch = self.root / "c019"
        self.assertEqual(self.cli(self.prefix, "branch", branch)[0], 0)
        (branch / "prefix-events.jsonl").write_text("")
        self.assertEqual(self.cli(branch, "resume", token)[0], 1)
        (self.prefix / "work" / "draft.txt").write_text("changed")
        self.assertEqual(self.cli(self.prefix, "snapshot")[0], 1)


if __name__ == "__main__":
    unittest.main()
