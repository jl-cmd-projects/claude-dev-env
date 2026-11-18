"""Names and paths of the archived work orders and receipts."""

from pathlib import Path


FIXTURE_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = FIXTURE_ROOT / "evidence"
ALL_CASE_FILENAMES = ("cases.json", "validation_cases.json", "staged_case.json")
ALL_ARCHIVE_FILENAMES = ("pilot.jsonl", "validation.jsonl", "staged.jsonl")
