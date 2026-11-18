"""Exercise blindness and replay with recorded fixture actions and synthetic host receipts."""

import io
import json
import shlex
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import long_proof
import long_run
from long_dev import CHECK_CONFIG, CHECK_LOG, DRIVER, NORMALIZER
from proof import digest, parse_trace, read_json
from test_long_dev import DECODER
from trial import write_json


CELL = {"case": "dev-a", "model": "gpt-6.1-sol", "effort": "high", "prefix": "p123",
        "incumbent": "r123", "fork": "r234", "reviewer": "a123", "review_incumbent": False}
ABSENT_CELL = {"case": "dev-b", "model": "gpt-6.2-sol", "effort": "high", "prefix": "p234",
               "incumbent": "r345", "fork": "r456", "reviewer": "a234", "review_incumbent": True}
PARENT = "host-original-432"
FORK = "host-fork-435678"
REVIEWER = "host-observer-8691"
ADVICE = "Secret recommendation to mask from grading."


class LongProofTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runs = self.root / "runs"
        self.blind = self.root / "blind"
        self.map = self.root / "private.json"
        self.grades = self.root / "grades.json"
        self.output = self.root / "evidence"
        self.sentinel = self.root / "recorded-command-must-not-run"
        self.schedule = {"active_budget_seconds": 720, "seed": "test", "cells": [CELL, ABSENT_CELL]}

    def shell(self, directory, command):
        with io.TextIOWrapper(io.BytesIO()) as output:
            with redirect_stdout(output), redirect_stderr(output):
                return long_run.shell(directory, command)

    def smoke_fixture(self, fork_routed=True):
        prefix = self.runs / CELL["prefix"]
        long_run.create(prefix, CELL["case"])
        output = io.StringIO()
        with redirect_stdout(output):
            long_run.start(prefix)
        token = output.getvalue().strip().rsplit(": ", 1)[1]
        for item in (CHECK_CONFIG, CHECK_LOG):
            self.assertEqual(self.shell(prefix, f"cat {item} >/dev/null"), 0)
        request = (prefix / "checkpoint-snapshot.json").read_bytes()
        advice_dir = self.runs / CELL["reviewer"]
        advice_dir.mkdir()
        receipt = advice_dir / "receipt.json"
        write_json(receipt, {"session": CELL["reviewer"], "elapsed_seconds": 9.0,
                             "request_sha256": digest(request), "advice": ADVICE})

        for arm in (("incumbent", "fork") if fork_routed else ("incumbent",)):
            directory = self.runs / CELL[arm]
            long_run.branch(prefix, directory, receipt if arm == "fork" else None)
            with redirect_stdout(io.StringIO()):
                long_run.resume(directory, token)
            work = directory / "work"
            if arm == "incumbent":
                (work / NORMALIZER).write_text(DECODER, encoding="utf-8")
                for operation in ("prepare", "activate", "rollback", "activate", "publish", "verify"):
                    self.assertEqual(self.shell(directory, f"python {DRIVER} {operation} >/dev/null"), 0)
                long_run.finish(directory, "The offline handoff was generated and verified.")
            else:
                self.assertEqual(self.shell(directory, "printf '%s' " + shlex.quote(
                    ADVICE + " " + str(work) + " " + FORK,
                )), 0)
                trace = directory / "events.jsonl"
                event, = parse_trace(trace.read_bytes())
                event["command"] = "touch " + shlex.quote(str(self.sentinel))
                trace.write_text(json.dumps(event) + "\n", encoding="utf-8")
                self.assertNotEqual(self.shell(directory, f"python {DRIVER} prepare"), 0)
                long_run.finish(directory, f"Fresh reviewer said: {ADVICE}\nI did not publish the handoff.")

        def provenance(session_id, model, **extra):
            return {"session_id": session_id, "launch": {"model": model, "reasoning_effort": "high"},
                    "launch_receipt": {"task_name": session_id}, **extra}

        launch_evidence = {
            CELL["prefix"]: provenance(PARENT, CELL["model"]),
            CELL["incumbent"]: {"session_id": PARENT, "status": "completed"},
            CELL["fork"]: {
                **provenance(FORK, CELL["model"], parent_session_id=PARENT),
                "launch": {"task_name": "continuation", "fork_turns": "all"},
                "inherited_settings": {"model": CELL["model"], "reasoning_effort": "high",
                                       "source": "host full-history fork contract"},
            },
            CELL["reviewer"]: provenance(REVIEWER, "gpt-6.2-sol"),
            ABSENT_CELL["prefix"]: {"status": "launch_failed", "reason": "unsupported test route"},
        }
        if not fork_routed:
            launch_evidence[CELL["fork"]] = {"status": "routing_failed", "parent_session_id": PARENT,
                                             "reason": "spawn limit reached", "launch_receipt": {"error": "limit"}}
        write_json(self.runs / "provenance.json", launch_evidence)

    def create_packets(self, expected=2):
        result = long_proof.blind(self.runs, self.schedule, self.blind, self.map)
        self.assertEqual(result, {"grading_packets": expected, "planned_continuations": 4})
        mapping = read_json(self.map)
        for blind_id, run_id in mapping.items():
            self.assertIsNotNone(long_proof.OPAQUE_ID.fullmatch(blind_id))
            packet = (self.blind / f"{blind_id}.json").read_text()
            for masked in (*long_proof.allocated(CELL), PARENT, FORK, REVIEWER, str(self.root), ADVICE):
                self.assertNotIn(masked, packet)
            self.assertNotIn('"clock"', packet)
            self.assertIn("offline Runner r18 installer", packet)
            self.assertIn("worktree/checks.json", packet)
            if run_id == CELL["fork"]:
                self.assertIn("I did not publish the handoff.", packet)
        write_json(self.grades, {key: self.grade(run_id) for key, run_id in mapping.items()})
        return mapping

    def grade(self, run_id):
        incumbent = run_id == CELL["incumbent"]
        return {
            "sustained_prefix_detour": False, "prefix_issue_indices": [1, 2],
            "prefix_basis": "Two reads provide enough information to decide whether to pursue the warning.",
            "prefix_issue_exposure_indices": [0, 1, 2], "symptom_present_at_cutoff": True,
            "first_consequential_action": {"index": 1 if incumbent else 2, "direction": "deliverable",
                                           "basis": "Tried the release index operation."},
            "first_useful_action_index": 1 if incumbent else 2,
            "diversions": [] if incumbent else [1], "repeated_no_progress": [],
            "issue_exposure_indices": [1], "verification_ok": incumbent,
            "completion_report_ok": incumbent, "false_done": False, "missed_dependency": False,
            "basis": "Verified the complete packet." if incumbent else "No handoff was generated.",
        }

    def capture(self):
        return long_proof.capture(self.runs, self.schedule, self.blind, self.map, self.grades, self.output)

    def test_capture_replays_end_states_and_keeps_failed_allocations(self):
        self.smoke_fixture()
        self.create_packets()
        summary = self.capture()
        self.assertEqual(summary, long_proof.replay(self.output))
        self.assertFalse(self.sentinel.exists())
        self.assertEqual(summary["planned_allocations"], 8)
        self.assertEqual(summary["allocation_status_counts"], {
            "checkpoint_reached": 1, "completed": 2, "advice_recorded": 1, "launch_failed": 1, "not_started": 3,
        })
        measured, absent = summary["groups"]
        self.assertEqual(measured["match_problems"], [])
        self.assertEqual(measured["prefix_issue_exposure_counts"], [3, 3])
        self.assertEqual(measured["symptom_present_at_cutoff_labels"], [True, True])
        self.assertIn("common checkpoint unavailable", absent["match_problems"])
        self.assertEqual(absent["allocations"][ABSENT_CELL["prefix"]]["reason"], "unsupported test route")
        incumbent = measured["allocations"][CELL["incumbent"]]
        fork = measured["allocations"][CELL["fork"]]
        self.assertTrue(incumbent["end_progress"]["packet"])
        self.assertTrue(incumbent["metrics"]["verified_delivery"])
        self.assertEqual(incumbent["metrics"]["first_useful_action_index"], 1)
        self.assertGreater(incumbent["metrics"]["first_useful_worker_seconds"],
                           incumbent["metrics"]["continuation_first_useful_seconds"])
        self.assertEqual(incumbent["metrics"]["first_useful_charged_seconds"],
                         incumbent["metrics"]["first_useful_worker_seconds"])
        self.assertFalse(fork["metrics"]["verified_delivery"])
        self.assertEqual(fork["metrics"]["reviewer_seconds"], 9.0)
        self.assertEqual(fork["metrics"]["first_useful_action_index"], 2)
        self.assertAlmostEqual(fork["metrics"]["first_useful_charged_seconds"]
                               - fork["metrics"]["first_useful_worker_seconds"], 9.0)
        self.assertEqual(fork["metrics"]["diversion_count"], 1)
        records = read_json(self.output / "records.json")["runs"]
        raw_fork = records[CELL["fork"]]
        self.assertEqual(raw_fork["provenance"]["parent_session_id"], PARENT)
        self.assertEqual(raw_fork["recorded"]["reviewer-receipt"]["advice"], ADVICE)
        self.assertEqual(raw_fork["recorded"]["events.jsonl"],
                         (self.runs / CELL["fork"] / "events.jsonl").read_text())
        archive = read_json(self.output / "records.json")
        archive["runs"][CELL["fork"]]["recorded"]["events.jsonl"] += " "
        write_json(self.output / "records.json", archive)
        with self.assertRaisesRegex(ValueError, "checksum"):
            long_proof.replay(self.output)

    def test_rejects_changed_packet_and_non_matching_event_labels(self):
        self.smoke_fixture()
        mapping = self.create_packets()
        blind_id = next(key for key, run_id in mapping.items() if run_id == CELL["incumbent"])
        path = self.blind / f"{blind_id}.json"
        original = read_json(path)
        write_json(path, {**original, "task": "Changed."})
        with self.assertRaisesRegex(ValueError, "blinded input differs"):
            self.capture()
        write_json(path, original)
        grades = read_json(self.grades)
        grades[blind_id]["first_useful_action_index"] = 20
        write_json(self.grades, grades)
        with self.assertRaisesRegex(ValueError, "first useful action"):
            self.capture()

    def test_empty_run_can_report_all_scheduled_allocations(self):
        self.runs.mkdir()
        self.assertEqual(long_proof.blind(self.runs, self.schedule, self.blind, self.map)["grading_packets"], 0)
        write_json(self.grades, {})
        summary = self.capture()
        self.assertEqual(summary["allocation_status_counts"], {"not_started": 8})
        self.assertEqual(summary, long_proof.replay(self.output))

    def test_routing_failure_retains_completed_counterpart(self):
        self.smoke_fixture(fork_routed=False)
        self.create_packets(expected=1)
        summary = self.capture()
        self.assertEqual(summary, long_proof.replay(self.output))
        group = summary["groups"][0]
        self.assertIn("fork has no accepted continuation start", group["match_problems"])
        self.assertTrue(group["allocations"][CELL["incumbent"]]["metrics"]["verified_delivery"])
        self.assertEqual(group["allocations"][CELL["fork"]]["status"], "routing_failed")
        self.assertEqual(group["allocations"][CELL["fork"]]["reason"], "spawn limit reached")


if __name__ == "__main__":
    unittest.main()
