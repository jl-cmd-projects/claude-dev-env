"""Record a matched continuation against an unchanged design delivery request."""

import importlib
import shutil
from unittest.mock import patch

import pivot_run
from long_run import workspace_tree
from proof import pinned_baseline, read_json
from trial import HERE, digest, write_json


PIN = pivot_run.PIN
BUDGET_SECONDS = pivot_run.BUDGET_SECONDS
CASES = ("ledger_ready", "ledger_gap", "preview")


def fixture(case):
    if case not in CASES:
        raise ValueError(f"Unknown design fixture: {case}")
    return importlib.import_module("design_slice_reserve" if case == "preview" else "design_slice_case")


def artifact_paths(case):
    return fixture(case).artifact_paths(case)


def prepare(directory, case, steady=True):
    original = fixture(case).history(case).rstrip() + "\n"
    if not original.strip() or pivot_run.UPDATE in original:
        raise ValueError("The fixture must present one unchanged user request.")
    instructions = pinned_baseline(PIN)
    directory.mkdir(parents=True, exist_ok=False)
    try:
        work = directory / "work"
        work.mkdir()
        fixture(case).prepare(work, case)
        (directory / "instructions.md").write_text(instructions, encoding="utf-8")
        (directory / "task.txt").write_text(original, encoding="utf-8")
        (directory / "operator-update.txt").touch()
        (directory / "events.jsonl").touch()
        write_json(directory / "initial-workspace.json", workspace_tree(work))
        write_json(directory / "run.json", {
            "case": case, "phase": "prefix", "mode": "steady", "pin": PIN, "budget_seconds": BUDGET_SECONDS,
            "input_sha256": pivot_run.hash_files(directory, pivot_run.INPUT_FILES),
        })
    except BaseException:
        shutil.rmtree(directory)
        raise


def review_trigger(directory, manifest, events, tree):
    logs = {path for event in events for path in event["changes"] if path.endswith(".log")}
    inspections = []
    last_change = 0
    for event in events:
        changes = sorted(set(event["changes"]) - logs)
        row = pivot_run.inspection_evidence({**event, "artifact_changes": changes}, logs)
        row.pop("artifact_changes", None)
        inspections.append(row)
        if changes:
            last_change = event["action"]
    recent = [row for row in inspections if row["action"] > last_change and row["substantive_inquiry"]]
    return {
        "eligible": len(recent) >= 2 and any(row["eligible"] for row in recent),
        "user_update_present": False, "user_goal_unchanged": True,
        "observations": inspections, "last_non_log_change_action": last_change,
        "inquiries_since_non_log_change": [row["action"] for row in recent],
    }


def review_advice(value):
    value = value.strip()
    return "" if value.casefold() in ("pass", "pass.") else value


def verify_review(directory):
    receipt_path, advice_path = directory / "review.json", directory / "advice.txt"
    if not receipt_path.exists() and not advice_path.exists():
        return
    if not receipt_path.is_file():
        raise ValueError("Advice requires a review receipt.")
    receipt = read_json(receipt_path)
    checkpoint = read_json(directory / "prefix-checkpoint.json")
    snapshot = (directory / "review-input.json").read_bytes()
    prompt = (HERE / "pivot_reviewer.txt").read_bytes() + b"\n" + snapshot
    advice = advice_path.read_text(encoding="utf-8").strip() if advice_path.exists() else ""
    if (not checkpoint["review_trigger"]["eligible"]
            or receipt.get("request_sha256") != digest(snapshot)
            or receipt.get("reviewer_prompt_sha256") != digest(prompt)
            or not isinstance(receipt.get("advice"), str)
            or advice != review_advice(receipt["advice"])
            or (advice_path.exists() and not advice)):
        raise ValueError("The review receipt is missing or mismatched for this checkpoint.")


def resume(directory, manifest):
    verify_review(directory)
    return pivot_resume(directory, manifest)


pivot_resume = pivot_run.resume


def pivot_fixture():
    return patch.multiple(
        pivot_run, CASES=CASES, module=fixture, prepare=prepare, artifact_paths=artifact_paths,
        review_trigger=review_trigger, resume=resume,
    )


def main():
    with pivot_fixture():
        return pivot_run.main()


if __name__ == "__main__":
    raise SystemExit(main())
