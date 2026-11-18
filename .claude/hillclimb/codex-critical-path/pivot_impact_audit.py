"""Audit the original pivot-study nominations and supplied review receipts."""
import argparse
import hashlib
import json
import subprocess
import types
from pathlib import Path
from unittest.mock import patch

import pivot_run
from proof import json_digest
from trial import HERE

PIN = "7019e04d459b3145ff7ae198ae9649535a21ba8d"
BASE = ".claude/hillclimb/codex-critical-path/"
ARCHIVE_SHA256 = "c4c26a5ab45791f4e1e559900d55621688a67319412dcde2112eefe012cca00c"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def data(path):
    return json.loads(path.read_bytes())


def pinned(name):
    return subprocess.check_output(["git", "show", f"{PIN}:{BASE}{name}"], cwd=HERE)


def historical_runner():
    module = types.ModuleType("historical_pivot_run")
    source = pinned("pivot_run.py")
    if sha(source) != "ed7fb254ab0e8d18b70daff1a33cb6777bffe055c1dd6a9394b77e50b2829441":
        raise ValueError("Unexpected historical runner.")
    exec(compile(source, "historical_pivot_run.py", "exec"), module.__dict__)
    return module


def audit_nominations(prefix, old):
    manifest = data(prefix / "run.json")
    checkpoint = data(prefix / "checkpoint.json") if (prefix / "checkpoint.json").exists() else None
    events = [json.loads(line) for line in (prefix / "events.jsonl").read_text().splitlines()]
    tree = data(prefix / "initial-workspace.json")
    rows = []
    for index, e in enumerate(events, 1):
        assert e["before_sha256"] == json_digest(tree)
        for path, change in e["changes"].items():
            if change["after"] is None:
                del tree[path]
            else:
                tree[path] = change["after"]
        assert e["after_sha256"] == json_digest(tree)
        at_boundary = bool(checkpoint and index == checkpoint["action_count"])
        if not (at_boundary or (manifest["mode"] == "steady" and index >= 2)):
            continue
        seen = events[:index]
        votes = []
        for answer in (False, True):
            with patch.object(old, "artifact_grade", return_value={"pass": answer}) as oracle:
                trigger = old.review_trigger(prefix, manifest, seen, tree)
                votes.append({"hidden_pass": answer, "oracle_called": oracle.called,
                              "eligible": trigger["eligible"], "goal_open": trigger["goal_open"]})
        recorded = checkpoint["review_trigger"]["eligible"] if at_boundary else False
        visible = pivot_run.review_trigger(prefix, manifest, seen, tree)["eligible"]
        rows.append({"corrected_visible_eligible": visible, "visible_matches": recorded == visible,
                     "action": index, "frozen_checkpoint": at_boundary, "recorded_eligible": recorded,
                     "both_match": all(recorded == v["eligible"] for v in votes), "counterfactuals": votes})
    return rows


def audit_receipt(root, row, original_role):
    prefix = root / row["id"]
    reviewer = root / row["reviewer"]
    if not reviewer.exists():
        return None
    candidate = root / row["candidate"]
    packet = (prefix / "review-input.json").read_bytes()
    request = (reviewer / "request.txt").read_bytes()
    source = data(reviewer / "receipt.json")
    copy = data(candidate / "review.json")
    advice = (candidate / "advice.txt").read_text()
    expected = source["advice"]
    displayed = "" if expected.strip().lower().rstrip(".") == "pass" else expected
    return {
        "checkpoint_sha256": sha(packet),
        "request_sha256": sha(request),
        "submitted_request_matches_role_and_packet": request == original_role + b"\n" + packet,
        "checkpoint_binds_packet": data(prefix / "checkpoint.json")["review_input_sha256"] == sha(packet),
        "consumed_packet_matches_prefix": (candidate / "review-input.json").read_bytes() == packet,
        "checkpoint_digest_present_and_correct": copy.get("request_sha256") == sha(packet),
        "original_request_digest_present_and_correct": source.get("request_sha256") == sha(request),
        "copied_request_digest_present_and_correct": copy.get("reviewer_prompt_sha256") == sha(request),
        "started_with_receipt": data(candidate / "started.json")["receipt_sha256"] == sha((candidate / "review.json").read_bytes()),
        "advice_matches": advice == displayed,
    }


def run(root):
    old = historical_runner()
    schedule = json.loads(pinned("pivot_schedule.json"))["rows"] + json.loads(pinned("pivot_steady_schedule.json"))["rows"]
    role = pinned("pivot_reviewer.txt")
    trials = {}
    for row in schedule:
        trials[row["id"]] = {"nominations": audit_nominations(root / row["id"], old),
                             "receipt": audit_receipt(root, row, role)}
    nom = [n for trial in trials.values() for n in trial["nominations"]]
    receipts = [trial["receipt"] for trial in trials.values() if trial["receipt"]]
    return {"runner_commit": PIN, "published_archive_sha256": ARCHIVE_SHA256, "prefixes": len(trials),
            "nomination_evaluations": len(nom), "evaluations_consulting_hidden_oracle": sum(n["counterfactuals"][0]["oracle_called"] for n in nom),
            "changed_decisions_under_either_hidden_answer": sum(not n["both_match"] for n in nom),
            "changed_decisions_with_visible_only_policy": sum(not row["visible_matches"] for row in nom),
            "review_receipts": len(receipts),
            "unbound_or_mismatched_receipts": sum(not all(v for v in receipt.values() if isinstance(v, bool)) for receipt in receipts),
            "trials": trials}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    answer = run(parser.parse_args().root.resolve())
    print(json.dumps(answer, indent=2, sort_keys=True))
