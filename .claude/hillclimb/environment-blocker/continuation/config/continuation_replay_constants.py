"""Study paths and pinned inputs shared across the four continuation cells."""

from pathlib import Path


CONTINUATION_ROOT = Path(__file__).resolve().parents[1]
CONTINUATION_EVIDENCE_PATH = CONTINUATION_ROOT / "evidence.jsonl"
CONTINUATION_CASES_PATH = CONTINUATION_ROOT / "cases.json"
BASELINE_LAUNCH_PATH = CONTINUATION_ROOT.parent / "evidence" / "launch.json"
ALL_ARMS = ("baseline", "revised")
LAUNCH_MESSAGE_SHA256 = "da06893726e740f18906899b6ed72bf98cddf19cd5b8f1082501220498152043"
ORDER_SHA256 = "860bfcbdec5af171bbc2dd0425b73c4b0dd9664bdfb2bb32d545cfae75ff2240"
