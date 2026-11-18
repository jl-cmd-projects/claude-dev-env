"""Stage opaque work orders and own their receiving desks for hosted Codex workers."""

import argparse
import json
import secrets
import sys
import tempfile
import time
from pathlib import Path

from install import digest
from receiver import Receiver


def serve(baseline, candidate, work, records, repeats):
    records.mkdir(parents=True, exist_ok=False)
    cases = json.loads(Path(__file__).with_name("cases.json").read_text())
    orders = {}
    started = {}
    for repeat in range(1, repeats + 1):
        for index, case in enumerate(cases):
            arms = [("baseline", baseline), ("candidate", candidate)]
            for arm, source in (arms if (index + repeat) % 2 else reversed(arms)):
                root = Path(tempfile.mkdtemp(prefix="order-", dir=work))
                prompt = (source / ".codex/codex-sol.md").read_bytes()
                checkpoint = json.loads((source / "install.json").read_text())
                if digest(prompt) != checkpoint["prompt_sha256"]:
                    raise ValueError("Source prompt differs from its installation receipt")
                (root / "AGENTS.md").write_bytes(prompt)
                (root / "order.md").write_text(case["prompt"] + "\n")
                receiver = Receiver(root, case)
                receiver.__enter__()
                orders[root.name] = (receiver, {
                    "arm": arm, "case": case["id"], "split": case["split"], "repeat": repeat,
                    "blind_id": secrets.token_hex(8), "work_id": root.name, **checkpoint,
                })
    manifest = [meta for _, meta in orders.values()]
    (records / "orders.json").write_text(json.dumps(manifest, indent=2))
    print(f"Ready with {len(orders)} orders", flush=True)
    for line in sys.stdin:
        action, *ids = line.split()
        for key in ids:
            receiver, meta = orders[key]
            if action == "start":
                if key in started or (records / (key + ".json")).exists():
                    raise ValueError("The worker already started")
                started[key] = time.monotonic()
            elif action in {"finish", "timeout"}:
                receiver.__exit__()
                state = receiver.score()
                seconds = round(time.monotonic() - started.pop(key), 2)
                status = "timeout" if seconds > 180 else action
                result = {
                    **meta, **state, "seconds": seconds, "status": status,
                    "state_pass": status == "finish" and state["receipt_goal"]
                    and not state["violations"] and not state["receiver_error"],
                }
                (records / (key + ".json")).write_text(json.dumps(result, indent=2))
                print(key, result["state_pass"], flush=True)
        if action == "quit":
            break
    for receiver, _ in orders.values():
        receiver.__exit__()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("records", type=Path)
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=2)
    args = parser.parse_args()
    serve(args.baseline, args.candidate, args.work, args.records, args.repeats)
