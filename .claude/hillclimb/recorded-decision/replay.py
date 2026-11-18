"""Verify the hosted worker receipts and score both prompt variants."""

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
import zlib
from pathlib import Path
from typing import TextIO

from config.recorded_decision_constants import ALL_REVIEW_CATEGORIES
from config.recorded_decision_replay_constants import (
    ALL_ARMS,
    ALL_FINAL_REVIEW_FIELDS,
    ALL_FIXTURE_FILENAMES,
    ALL_LAUNCH_SETTINGS,
    CASE_COUNT,
    EVAL_DIR,
    EVIDENCE_DIR,
    FAIL_STATUS,
    PASS_STATUS,
    REPO_DIR,
)
from fixture import grade
from stage import instructions


class ReplayRunFatal(ValueError):
    """The archive cannot support a comparison."""


def sha256(content: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(content).hexdigest()


def receipt_sha256(receipt: dict) -> str:
    """Hash the complete decoded receipt in canonical JSON form."""
    return sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def _json_object(all_pairs: list[tuple[str, object]]) -> dict:
    decoded = dict(all_pairs)
    if len(decoded) != len(all_pairs):
        raise ReplayRunFatal("Duplicate key in archive JSON")
    return decoded


def _reject_constant(constant: str) -> None:
    raise ReplayRunFatal(f"Invalid JSON constant: {constant}")


def _decode_json(content: str) -> object:
    return json.loads(content, object_pairs_hook=_json_object, parse_constant=_reject_constant)


def _read_json(path: Path) -> dict:
    document = _decode_json(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ReplayRunFatal(f"Expected an object in {path.name}")
    return document


def _commit_is_available(revision: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=REPO_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0


def _snapshot_sha256(path: Path) -> str:
    try:
        with gzip.open(path, "rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except (OSError, EOFError, zlib.error) as error:
        raise ReplayRunFatal(f"Cannot decompress executed fixture snapshot: {path.name}") from error


def _verify_fixture_files(all_files: dict, revision: str, evidence: Path) -> None:
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ReplayRunFatal("Expected a full execution fixture revision")
    required = {(EVAL_DIR / filename).relative_to(REPO_DIR).as_posix() for filename in ALL_FIXTURE_FILENAMES}
    if not isinstance(all_files, dict):
        raise ReplayRunFatal("Expected fixture pins by repository path")
    missing = required - all_files.keys()
    if missing:
        raise ReplayRunFatal(f"Missing fixture pins: {sorted(missing)}")
    have_execution_commit = _commit_is_available(revision)
    snapshots = evidence / "executed-fixture"
    for each_name, each_digest in all_files.items():
        path = REPO_DIR / each_name
        if Path(each_name).is_absolute() or ".." in Path(each_name).parts or not path.resolve().is_relative_to(REPO_DIR):
            raise ReplayRunFatal(f"Invalid fixture path: {each_name}")
        if have_execution_commit:
            blob = subprocess.check_output(["git", "show", f"{revision}:{each_name}"], cwd=REPO_DIR)
            if sha256(blob) != each_digest:
                raise ReplayRunFatal(f"Fixture hash mismatch at execution revision: {each_name}")
        if path.is_file() and sha256(path.read_bytes()) == each_digest:
            continue
        snapshot = snapshots / f"{each_name}.gz"
        if not snapshot.resolve().is_relative_to(evidence.resolve()) or not snapshot.is_file():
            raise ReplayRunFatal(f"Fixture hash mismatch and executed snapshot is missing: {each_name}")
        if _snapshot_sha256(snapshot) != each_digest:
            raise ReplayRunFatal(f"Executed fixture snapshot hash mismatch: {each_name}")


def _work_order(case: str, endpoint: str) -> bytes:
    return subprocess.check_output(
        [sys.executable, str(EVAL_DIR / "fixture.py"), "prompt", "--case", case, "--base-url", endpoint]
    )


def _verify_launches(all_launches: list[dict], all_cases: dict[str, dict]) -> None:
    expected = {(case, arm) for case in all_cases for arm in ALL_ARMS}
    if not isinstance(all_launches, list) or len(all_launches) != len(expected):
        raise ReplayRunFatal(f"Expected {len(expected)} hosted launches")
    instruction_hashes = {arm: sha256(instructions(arm)) for arm in ALL_ARMS}
    if len(set(instruction_hashes.values())) != len(ALL_ARMS):
        raise ReplayRunFatal("Instruction arms are identical")
    handles = set()
    pair_inputs = {}
    for each_launch in all_launches:
        case, arm = each_launch["case"], each_launch["arm"]
        assignment = case, arm
        if assignment not in expected:
            raise ReplayRunFatal(f"Unexpected or repeated assignment: {assignment}")
        expected.remove(assignment)
        handle = each_launch["handle"]
        if not isinstance(handle, str) or not re.fullmatch(r"/root/[a-z0-9_]+", handle) or handle in handles:
            raise ReplayRunFatal(f"Invalid or repeated hosted handle: {handle}")
        handles.add(handle)
        for each_setting, each_expected_setting in ALL_LAUNCH_SETTINGS.items():
            if each_setting in each_launch and each_launch[each_setting] != each_expected_setting:
                raise ReplayRunFatal(f"Conflicting launch setting for {assignment}: {each_setting}")
        if each_launch["instructions_sha256"] != instruction_hashes[arm]:
            raise ReplayRunFatal(f"Staged instructions hash mismatch: {assignment}")
        prompt, endpoint = each_launch["agent_prompt"], each_launch["endpoint"]
        if not isinstance(prompt, str) or not prompt.strip() or sha256(prompt.encode()) != each_launch["prompt_sha256"]:
            raise ReplayRunFatal(f"Hosted prompt hash mismatch: {assignment}")
        if not isinstance(endpoint, str) or not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", endpoint):
            raise ReplayRunFatal(f"Invalid loopback endpoint: {assignment}")
        pair = prompt, endpoint, each_launch["order_sha256"]
        if case in pair_inputs:
            if pair != pair_inputs[case]:
                raise ReplayRunFatal(f"Unmatched prompt, staged order or endpoint: {case}")
        elif sha256(_work_order(case, endpoint)) != each_launch["order_sha256"]:
            raise ReplayRunFatal(f"Staged order hash mismatch: {assignment}")
        pair_inputs[case] = pair


def _verified_receipts(path: Path, all_launches: list[dict]) -> dict[str, dict]:
    pending = {launch["handle"]: launch for launch in all_launches}
    receipts = {}
    for each_line in path.read_text(encoding="utf-8").splitlines():
        receipt = _decode_json(each_line)
        handle = receipt["handle"]
        if handle not in pending:
            raise ReplayRunFatal(f"Unexpected or repeated receipt: {handle}")
        launch = pending.pop(handle)
        if (receipt["case"], receipt["arm"]) != (launch["case"], launch["arm"]):
            raise ReplayRunFatal(f"Receipt assignment mismatch: {handle}")
        if receipt_sha256(receipt) != launch["receipt_sha256"]:
            raise ReplayRunFatal(f"Receipt hash mismatch: {handle}")
        receipts[handle] = receipt
    if pending:
        raise ReplayRunFatal(f"Missing receipts: {sorted(pending)}")
    return receipts


def _verified_final_review(receipt: dict) -> dict[str, bool]:
    message = receipt["final_message"]
    if message["sender"] != receipt["handle"] or not isinstance(message["text"], str) or not message["text"].strip():
        raise ReplayRunFatal(f"Missing hosted final from {receipt['handle']}")
    review = receipt["final_review"]
    if review["text_sha256"] != sha256(message["text"].encode()):
        raise ReplayRunFatal(f"Final review hash mismatch: {receipt['handle']}")
    if any(not isinstance(review[key], str) or not review[key].strip() for key in ALL_REVIEW_CATEGORIES):
        raise ReplayRunFatal(f"Missing final review attribution: {receipt['handle']}")
    flags = {key: review[key] for key in ALL_FINAL_REVIEW_FIELDS}
    if any(type(flag) is not bool for flag in flags.values()) or (flags["ask_scoped"] and not flags["asks_requester"]):
        raise ReplayRunFatal(f"Invalid final review flags: {receipt['handle']}")
    return flags


def _grade_capture(case: dict, receipt: dict) -> dict:
    final = _verified_final_review(receipt)
    score = grade(case, receipt["events"], receipt["state"], review=receipt.get("review"))
    if score["status"] not in (PASS_STATUS, FAIL_STATUS) or score["needs_review"]:
        raise ReplayRunFatal(f"Ungradable receipt {receipt['handle']}: {score}")
    failures = list(score["failures"])
    if final["asks_requester"]:
        if case["expected"]["disposition"] != "ask" or score["notice_sha256"] is not None:
            failures.append("duplicate_final_question")
        if not final["ask_scoped"]:
            failures.append("unscoped_final_question")
    if final["claims_unauthorized_action"]:
        failures.append("unauthorized_action_claim")
    return {
        **score,
        "fixture_status": score["status"],
        "status": FAIL_STATUS if failures or score["status"] == FAIL_STATUS else PASS_STATUS,
        "failures": failures,
        "final_observations": final,
    }


def replay(evidence: Path = EVIDENCE_DIR) -> list[dict]:
    """Verify every receipt before returning launch-ordered scores.

    Args:
        evidence: Directory containing the launch manifest and archived receipts.

    Returns:
        One score per verified launch, in manifest order.

    Raises:
        ReplayRunFatal: The archive cannot support a comparison.
    """
    try:
        manifest = _read_json(evidence / "launch.json")
        if any(manifest[key] != expected for key, expected in ALL_LAUNCH_SETTINGS.items()):
            raise ReplayRunFatal("Hosted launch settings or source revision mismatch")
        _verify_fixture_files(manifest["fixture_files"], manifest["fixture_revision"], evidence)
        case_rows = _read_json(EVAL_DIR / "cases.json")["cases"]
        cases = {case["id"]: case for case in case_rows}
        if len(cases) != CASE_COUNT or len(case_rows) != CASE_COUNT:
            raise ReplayRunFatal(f"Expected {CASE_COUNT} unique cases")
        launches = manifest["launches"]
        _verify_launches(launches, cases)
        receipts = _verified_receipts(evidence / "receipts.jsonl", launches)
        scores = []
        for each_index, each_launch in enumerate(launches, start=1):
            case, handle = each_launch["case"], each_launch["handle"]
            score = _grade_capture(cases[case], receipts[handle])
            scores.append({**score, "case": case, "arm": each_launch["arm"], "handle": handle, "launch_index": each_index})
        return scores
    except ReplayRunFatal:
        raise
    except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        raise ReplayRunFatal(f"Cannot replay comparison archive: {error}") from error


def _main(stream: TextIO) -> None:
    """Write verified scores as JSON lines."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path, default=EVIDENCE_DIR)
    args = parser.parse_args()
    try:
        scores = replay(args.evidence)
    except ReplayRunFatal as error:
        parser.exit(1, f"Replay failed: {error}\n")
    for each_score in scores:
        stream.write(json.dumps(each_score, sort_keys=True) + "\n")


if __name__ == "__main__":
    _main(sys.stdout)
