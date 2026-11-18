"""Stage opaque work orders and own their receiving desks for hosted Codex workers."""

import argparse
import json
import secrets
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from install import digest
from receiver import Receiver


def serve(baseline, candidate, work, records, repeats, case_file):
    records.mkdir(parents=True, exist_ok=False)
    cases = json.loads(case_file.read_text())
    arms = []
    for arm, source in (("baseline", baseline), ("candidate", candidate)):
        prompt = (source / ".codex/codex-sol.md").read_bytes()
        checkpoint = json.loads((source / "install.json").read_text())
        if digest(prompt) != checkpoint["prompt_sha256"]:
            raise ValueError("Source prompt differs from its installation receipt")
        arms.append((arm, prompt, checkpoint))
    if arms[0][1] == arms[1][1]:
        raise ValueError("The two hosted prompts are identical")
    with ExitStack() as desks:
        orders = {}
        started = {}
        for repeat in range(1, repeats + 1):
            for index, case in enumerate(cases):
                for arm, prompt, checkpoint in (arms if (index + repeat) % 2 else reversed(arms)):
                    root = Path(tempfile.mkdtemp(prefix="order-", dir=work))
                    (root / "AGENTS.md").write_bytes(prompt)
                    (root / "order.md").write_text(case["prompt"] + "\n")
                    receiver = desks.enter_context(Receiver(root, case))
                    if (root / "order.md").read_text() != case["prompt"] + "\n":
                        raise ValueError("Use a case-sensitive work directory for these frozen filenames")
                    orders[root.name] = (receiver, {
                        "arm": arm, "case": case["id"], "split": case["split"], "repeat": repeat,
                        "contract": case,
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
                    receipt_record = {
                        **meta, **state, "seconds": seconds, "status": status,
                        "state_pass": status == "finish" and state["receipt_goal"]
                        and not state["violations"] and not state["receiver_error"],
                    }
                    (records / (key + ".json")).write_text(json.dumps(receipt_record, indent=2))
                    print(key, receipt_record["state_pass"], flush=True)
            if action == "quit":
                break



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("records", type=Path)
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=2)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    args = parser.parse_args()
    serve(args.baseline, args.candidate, args.work, args.records, args.repeats, args.cases)
