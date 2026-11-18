import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from handoff_holdout import DRAFTS, WAIT_COMMAND, grade, prepare, read_json, record_end, replay_command, start


class HandoffHoldoutTest(unittest.TestCase):
    def test_queued_replies_separate_usable_commands_from_correct_prose(self):
        with tempfile.TemporaryDirectory() as scratch, contextlib.redirect_stdout(io.StringIO()):
            for case, expected_wait, expected_handback in (
                ("omitted", True, False), ("arrived", False, False), ("waiting", True, True),
            ):
                with self.subTest(case=case):
                    directory = Path(scratch) / case
                    prepare(directory, case, "baseline", Path(scratch) / "unused.txt")
                    start(directory)
                    started = read_json(directory / "started.json")["monotonic"]
                    record_end(directory, started, "send-draft", DRAFTS[case])
                    result = grade(directory)
                    self.assertEqual(result["verdict_facts"], {"count": True, "wait": expected_wait})
                    self.assertEqual(result["runnable_handback"], expected_handback)
                    self.assertTrue(result["checkout_preserved"])
                    self.assertTrue(result["within_budget"])

    def test_only_candidate_overlay_changes_matched_inputs(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            delta = root / "overlay.txt"
            delta.write_text("Dispatch check fixture.\n")
            prepare(root / "first", "arrived", "baseline", delta)
            prepare(root / "second", "arrived", "candidate", delta)
            first = read_json(root / "first/run.json")
            second = read_json(root / "second/run.json")
            self.assertEqual(first["match_key"], second["match_key"])
            self.assertNotEqual(first["instructions_sha256"], second["instructions_sha256"])
            self.assertEqual((root / "second/intervention.txt").read_bytes(), delta.read_bytes().strip())

    def test_replay_requires_changing_data_and_accepts_bounded_missing_wait(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            for case, oldest_seconds in (("omitted", 420), ("arrived", 780), ("waiting", None)):
                with self.subTest(case=case):
                    directory = root / case
                    prepare(directory, case, "baseline", root / "unused.txt")
                    replay = replay_command(directory / "initial", WAIT_COMMAND, case, True)
                    self.assertTrue(replay["pass"])
                    self.assertEqual(replay["expected"], {"pending": 6, "oldest_wait_seconds": oldest_seconds})
                    self.assertEqual(replay["missing_wait_reported"], oldest_seconds is None)
            self.assertFalse(replay_command(root / "omitted/initial", "printf 'pending=5\\n'", "omitted", True)["pass"])


if __name__ == "__main__":
    unittest.main()
