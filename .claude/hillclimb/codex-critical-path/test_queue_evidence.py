import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from queue_evidence import run_summary
from trial import PIN, write_json


def event(relevance, seconds):
    return {"observation": {"relevance": relevance}, "seconds": 0.1,
            "clock": {"total_elapsed_seconds": seconds}}


class ReceiptTiming(unittest.TestCase):
    def summarize(self, phase, trace, first):
        with tempfile.TemporaryDirectory() as scratch:
            directory = Path(scratch)
            write_json(directory / "prefix-checkpoint.json", {"clock": {"worker_elapsed_seconds": 180}})
            result = {"manifest": {"pin": PIN, "budget_seconds": 1500, "phase": phase},
                      "eligible_actions": [], "outcome": None}
            mark = {"first_useful_after_receipt": first, "first_consequential_after_receipt": first,
                    "diversions": [], "repeated_no_progress": [], "necessary_waits": [],
                    "sustained_detour": False, "verification_ok": False,
                    "false_done": False, "missed_dependency": False}
            with patch("queue_evidence.events", return_value=trace), patch("queue_evidence.replay", return_value=result):
                return run_summary(directory, mark)

    def test_command_delivering_receipt_cannot_be_a_response_to_it(self):
        trace = [event("unknown", 120), event("optional", 152), event("optional", 161)]
        with self.assertRaises(ValueError):
            self.summarize("prefix", trace, 2)
        outcome = self.summarize("prefix", trace, 3)
        self.assertEqual(outcome["charged_seconds_receipt_to_useful"], 9)

    def test_continuation_includes_review_time_from_common_cutoff(self):
        outcome = self.summarize("continuation", [event("optional", 195)], 1)
        self.assertEqual(outcome["charged_seconds_receipt_to_useful"], 15)


if __name__ == "__main__":
    unittest.main()
