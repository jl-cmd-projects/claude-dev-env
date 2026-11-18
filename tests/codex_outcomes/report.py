"""Join state evidence with a blinded review of each worker's reply."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def summarize(directory: Path, ratings_path: Path) -> list[dict]:
    blind = json.loads((directory / "blind.json").read_text())
    ratings = json.loads(ratings_path.read_text())
    expected_ids = {item["id"] for item in blind}
    if set(ratings) != expected_ids or len(expected_ids) != len(blind):
        raise ValueError("A rating is required for every distinct blinded attempt")
    groups = defaultdict(list)
    records = [json.loads(p.read_text()) for p in directory.glob("*/*/*/result.json")]
    manifest = json.loads((directory / "manifest.json").read_text())
    planned = {
        (case, repeat, arm) for case in manifest["cases"] for repeat in range(1, manifest["repeats"] + 1)
        for arm in manifest["arms"]
    }
    if {(row["case"], row["repeat"], row["arm"]) for row in records} != planned:
        raise ValueError("Results are missing from the scheduled battery")
    if {row["blind_id"] for row in records} != expected_ids or len(records) != len(expected_ids):
        raise ValueError("The results and blind packet differ")
    contracts = set()
    sources = defaultdict(set)
    pairs = defaultdict(dict)
    for row in records:
        contracts.add(tuple(row[k] for k in (
            "codex", "model", "effort", "budget_seconds", "dataset", "context_sha256", "hooks_sha256",
        )))
        sources[row["arm"]].add((row["revision"], row["prompt_sha256"]))
        pair = pairs[row["case"], row["repeat"]]
        if row["arm"] in pair:
            raise ValueError("Duplicate arm in a comparison")
        pair[row["arm"]] = row
        rating = ratings[row["blind_id"]]
        dimensions = ("false_done", "unnecessary_escalation", "incomplete_blocker_report", "unneeded_continuation")
        if not isinstance(rating.get("evidence"), str) or not rating["evidence"].strip():
            raise ValueError("Each judgment needs a source or quoted reply")
        if any(type(rating.get(k)) is not bool for k in dimensions):
            raise ValueError("Each judgment needs four boolean decisions")
        passed = row["state_pass"] and not any(rating[k] for k in dimensions)
        groups[row["case"], row["arm"]].append({
            **row, **{key: rating[key] for key in dimensions}, "passed": passed,
        })
    if len(contracts) != 1:
        raise ValueError("The launch conditions differ")
    if any(len(source) != 1 for source in sources.values()):
        raise ValueError("A comparison arm changed its source")
    prompt_hashes = {digest for source in sources.values() for _, digest in source}
    if len(prompt_hashes) != len(sources):
        raise ValueError("Comparison arms used identical prompts")
    arms = {row["arm"] for row in records}
    if any(set(pair) != arms for pair in pairs.values()):
        raise ValueError("The arms do not cover matched cases and repeats")
    summaries = []
    for (case, arm), rows in sorted(groups.items()):
        usage = [r["usage"] for r in rows if r["usage"]]
        summaries.append({
            "case": case, "split": rows[0]["split"], "arm": arm,
            "attempts": len(rows), "passed": sum(r["passed"] for r in rows),
            "state_passed": sum(r["state_pass"] for r in rows),
            "violations": sum(bool(r["violations"]) for r in rows),
            **{key: sum(r[key] for r in rows) for key in dimensions},
            "timeouts": sum(r["status"] == "timeout" for r in rows),
            "mean_seconds": round(mean(r["seconds"] for r in rows), 2),
            "reported_tokens": sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usage),
            "attempts_with_usage": len(usage),
            "turns": sum(r["turns"] for r in rows),
        })
    return summaries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("ratings", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.results, args.ratings), indent=2))
