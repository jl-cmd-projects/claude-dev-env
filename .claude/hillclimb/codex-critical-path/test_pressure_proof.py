"""Exercise proof replay with staged console commands and masked trial evidence."""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pressure_proof as proof
import pressure_run as runner
from proof import read_json
from trial import write_json


COUNTERS = r"Get-Counter '\Processor(_Total)\% Processor Time','\Memory\Available MBytes' -MaxSamples 5"
ARCHIVE = "Get-ChildItem captures/memory/*.csv | ForEach-Object { Import-Csv $_.FullName -Delimiter ';' }"


def clock(seconds):
    return {"elapsed_seconds": seconds, "within_budget": seconds < runner.BUDGET_SECONDS,
            "remaining_seconds": max(0, runner.BUDGET_SECONDS - seconds)}


def command(directory, seconds, code):
    with patch.object(runner, "clock", side_effect=[clock(seconds), clock(seconds + 3), clock(seconds + 3)]):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return runner.shell(directory, "powershell", code)


def mark(entry, excerpt, count, useful):
    return {
        "packet_sha256": entry["packet_sha256"], "ground_sha256": entry["ground_sha256"],
        "delivery": True, "limits": True, "usable_command": True, "command_excerpt": excerpt,
        "first_consequential_action": 1, "first_useful_action": useful,
        "side_actions": [], "mixed_actions": [], "repeated_no_progress_actions": [], "irrelevance_knowable_after": count,
        "sustained_detour": False, "missed_dependency": False, "false_done": False,
        "unassisted_incomplete": False, "nudge_needed": False, "basis": "Fixture verdict and readings.",
    }


@unittest.skipUnless(shutil.which("pwsh"), "PowerShell is required for recorded console commands")
class PressureProofTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.root, self.output = base / "private", base / "panel"
        self.root.mkdir()
        self.allocations = proof.checked_schedule()
        self.launches = {row["id"]: {"status": "failed", "model": row["model"],
                                      "reasoning_effort": row["reasoning_effort"], "receipt": {"failure": "capacity"}}
                         for row in self.allocations}

    def start(self, case, arm="baseline"):
        row = next(row for row in self.allocations if row["case"] == case and row["arm"] == arm)
        key = row["id"]
        self.launches[key].update(status="opened", receipt={"task_name": f"/root/{key}"}, session_id=f"worker-{key}")
        write_json(self.root / proof.LAUNCHES, self.launches)
        directory = self.root / key
        runner.create(directory, case, arm)
        with redirect_stdout(io.StringIO()):
            runner.start(directory)
        return directory

    def finish(self, directory, reply):
        with patch.object(runner, "clock", return_value=clock(60)):
            runner.finish(directory, reply)

    def test_blind_and_replay_native_sampled_before_and_after_jobs(self):
        directory = self.start("native", "candidate")
        case_id = directory.name
        self.assertEqual(command(directory, 9, "poolmon.exe /b"), 0)
        self.assertEqual(command(directory, 46, COUNTERS + "; poolmon.exe /b"), 0)
        self.finish(directory, f"CPU trended lower. The pool remains high after jobs completed.\n{COUNTERS}\n"
                               f"{directory / 'work'} worker-{case_id} gpt-6.1-sol candidate arm")
        result = proof.blind(self.root, self.output)
        self.assertEqual(result, {"packets": 12, "pending_grade": 1})
        entries = read_json(self.root / proof.MANIFEST)["entries"]
        opaque, entry = next((opaque, entry) for opaque, entry in entries.items() if entry["id"] == case_id)
        packet = read_json(self.output / f"{opaque}.json")
        card = read_json(self.output / f"{opaque}.ground.json")
        self.assertEqual([0, 0, 0, 2, 4], [row["completed_jobs"] for row in card["frames"]])
        for private in (case_id, "native", "candidate arm", "gpt-6.1-sol", str(directory), f"worker-{case_id}"):
            self.assertNotIn(private, packet["first_terminal_answer"])
        self.assertNotIn("id", read_json(self.output / "checksums.json")[opaque])
        grades = {"schema": 1, "judge": {"id": "panel", "method": "masked review"},
                  "grades": {opaque: mark(entry, COUNTERS, 2, 1)}}
        write_json(self.root / proof.GRADES, grades)
        replay = proof.replay(self.root)
        trial = replay["trials"][case_id]
        self.assertEqual(trial["first_pass_delivery"], "verified")
        self.assertEqual(trial["measures"]["first_useful_seconds"], 12)
        self.assertEqual(replay["arms"]["candidate"]["outcomes"], {"finished": 1, "launch-failed": 5})
        self.assertEqual(replay["historical_operator_nudge_observed"], 1)
        self.assertEqual(replay["replay_nudges_observed_in_first_pass"], 0)
        grades["grades"][opaque]["ground_sha256"] = "changed"
        write_json(self.root / proof.GRADES, grades)
        with self.assertRaisesRegex(ValueError, "sealed grading packet"):
            proof.replay(self.root)

    def test_archive_attempt_is_not_a_telemetry_read(self):
        directory = self.start("archive")
        self.assertEqual(command(directory, 46, "Get-ChildItem captures/memory"), 0)
        command(directory, 50, ".\\ops\\Show-MemoryArchive.ps1")
        self.finish(directory, "The archive tool did not return samples.")
        run = proof.study(self.root)[directory.name]
        oracle = proof.telemetry(run)
        self.assertFalse(oracle["coverage_across_completed_jobs"]["file_tag"])
        self.assertTrue(oracle["reviewable_sources"])

    def test_direct_archive_read_covers_job_transitions(self):
        directory = self.start("archive")
        self.assertEqual(command(directory, 46, COUNTERS), 0)
        self.assertEqual(command(directory, 50, ARCHIVE), 0)
        self.finish(directory, "Pool and CPU pressure declined as jobs finished.")
        run = proof.study(self.root)[directory.name]
        self.assertTrue(proof.telemetry(run)["corroborated"])

    def test_same_window_counter_points_do_not_span_job_transition(self):
        directory = self.start("native")
        self.assertEqual(command(directory, 9, COUNTERS + "; poolmon.exe /?"), 0)
        self.finish(directory, "One tagged snapshot is not yet available.")
        oracle = proof.telemetry(proof.study(self.root)[directory.name])
        self.assertFalse(oracle["corroborated"])
        self.assertFalse(oracle["coverage_across_completed_jobs"]["cpu"])
        self.assertNotIn("file_tag", oracle["actions"][0]["signals"])

    def test_post_nudge_score_retains_the_original_incomplete_trial(self):
        source = self.start("native")
        key = source.name
        self.assertEqual(command(source, 9, "poolmon.exe /b"), 0)
        self.finish(source, "The service stop improved free memory.")
        proof.blind(self.root, self.output)
        entry_id, entry = next((blind_id, entry) for blind_id, entry in read_json(self.root / proof.MANIFEST)["entries"].items()
                               if entry["id"] == key)
        grade = mark(entry, None, 1, None)
        grade.update(delivery=False, limits=False, usable_command=False, unassisted_incomplete=True, nudge_needed=True)
        judge = {"id": "panel", "method": "masked review"}
        write_json(self.root / proof.GRADES, {"schema": 1, "judge": judge, "grades": {entry_id: grade}})
        target = self.root / "rescued"
        runner.recover(source, target)
        with redirect_stdout(io.StringIO()):
            runner.start(target, resume=True)
        self.assertEqual(command(target, 61, COUNTERS + "; poolmon.exe /b"), 0)
        with patch.object(runner, "clock", return_value=clock(70)):
            runner.finish(target, f"CPU declined, available memory stayed low and tagged pool persisted.\n{COUNTERS}")
        rescue = {"directory": target.name, "session_id": self.launches[key]["session_id"],
                  "nudge": proof.NUDGE, "receipt": {"task_name": f"/root/{key}"}}
        write_json(self.root / proof.RESCUES, {key: rescue})
        self.assertEqual(proof.replay(self.root)["rescues_pending_grade"], [key])
        proof.blind_rescue(self.root, self.output.parent / "rescue_panel")
        opaque, rescued = next(iter(read_json(self.root / proof.RESCUE_MANIFEST)["entries"].items()))
        write_json(self.root / proof.RESCUE_GRADES,
                   {"schema": 1, "judge": judge, "grades": {opaque: mark(rescued, COUNTERS, 1, 1)}})
        replay = proof.replay(self.root)
        self.assertEqual(replay["observed_post_pass_nudges"], 1)
        self.assertEqual(replay["trials"][key]["first_pass_delivery"], "incomplete")
        self.assertEqual(replay["rescues"][key]["post_nudge_delivery"], "verified")
        self.assertEqual(replay["rescues"][key]["measures"]["first_useful_seconds_after_nudge"], 4)
        rescue["nudge"] += " Try the native tool."
        write_json(self.root / proof.RESCUES, {key: rescue})
        with self.assertRaisesRegex(ValueError, "same-worker nudge receipt"):
            proof.replay(self.root)

    def test_command_excerpt_is_parsed_without_evaluation(self):
        self.assertEqual(proof.command_syntax(COUNTERS)["status"], "parsed")
        self.assertEqual(proof.command_syntax("if (")["status"], "syntax-error")
        self.assertEqual(proof.command_syntax("Stop-Process -Id 100")["status"], "state-change")
        self.assertEqual(proof.command_syntax("'only a string'")["status"], "no-command")


if __name__ == "__main__":
    unittest.main()
