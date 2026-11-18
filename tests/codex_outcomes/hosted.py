"""Stage opaque work orders and own their receiving desks for hosted Codex workers."""

import argparse
import json
import secrets
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from typing import TextIO

from completion_eval.config import study
from completion_eval.errors import EvidenceRunFatal
from install import digest
from receiver import Receiver


def serve(baseline: Path, candidate: Path, work: Path, records: Path, repeats: int, case_file: Path,
          status_stream: TextIO = sys.stdout) -> None:
    """Stage workspaces, serve requests, and finalize their receiving journals.

    Args:
        baseline: Baseline installation directory.
        candidate: Trial installation directory.
        work: Parent for isolated participant workspaces.
        records: New controller-owned record directory.
        repeats: Number of paired runs per case.
        case_file: Frozen work-order specifications.
        status_stream: Destination for controller status.

    Raises:
        EvidenceRunFatal: An input or worker lifecycle is inconsistent.
    """
    records.mkdir(parents=True, exist_ok=False)
    cases = json.loads(case_file.read_text())
    arms = []
    for each_arm, each_source in ((study.BASELINE_ARM, baseline), (study.CANDIDATE_ARM, candidate)):
        each_prompt = (each_source / ".codex/codex-sol.md").read_bytes()
        each_checkpoint = json.loads((each_source / "install.json").read_text())
        if digest(each_prompt) != each_checkpoint["prompt_sha256"]:
            raise EvidenceRunFatal("Source prompt differs from its installation receipt")
        arms.append((each_arm, each_prompt, each_checkpoint))
    if arms[0][1] == arms[1][1]:
        raise EvidenceRunFatal("The two hosted prompts are identical")
    with ExitStack() as desks:
        orders = {}
        started = {}
        for each_repeat in range(1, repeats + 1):
            for each_index, each_case in enumerate(cases):
                for each_arm, each_prompt, each_checkpoint in (arms if (each_index + each_repeat) % len(arms) else reversed(arms)):
                    root = Path(tempfile.mkdtemp(prefix="order-", dir=work))
                    (root / "AGENTS.md").write_bytes(each_prompt)
                    (root / "order.md").write_text(each_case["prompt"] + "\n")
                    receiver = desks.enter_context(Receiver(root, each_case))
                    if (root / "order.md").read_text() != each_case["prompt"] + "\n":
                        raise EvidenceRunFatal("Use a case-sensitive work directory for these frozen filenames")
                    orders[root.name] = (receiver, {
                        "arm": each_arm, "case": each_case["id"], "split": each_case["split"], "repeat": each_repeat,
                        "contract": each_case,
                        "blind_id": secrets.token_hex(study.BLIND_ID_BYTES), "work_id": root.name, **each_checkpoint,
                    })
        manifest = [meta for _, meta in orders.values()]
        (records / "orders.json").write_text(json.dumps(manifest, indent=study.JSON_INDENT))
        status_stream.write(f"Ready with {len(orders)} orders\n")
        status_stream.flush()
        for each_line in sys.stdin:
            action, *ids = each_line.split()
            for each_key in ids:
                receiver, meta = orders[each_key]
                if action == "start":
                    if each_key in started or (records / (each_key + study.JSON_EXTENSION)).exists():
                        raise EvidenceRunFatal("The worker already started")
                    started[each_key] = time.monotonic()
                elif action in {"finish", "timeout"}:
                    receiver.__exit__()
                    state = receiver.score()
                    seconds = round(time.monotonic() - started.pop(each_key), study.TIMING_PRECISION)
                    status = "timeout" if seconds > study.APPROVED_SECONDS else action
                    receipt_record = {
                        **meta, **state, "seconds": seconds, "status": status,
                        "state_pass": status == "finish" and state["receipt_goal"]
                        and not state["violations"] and not state["receiver_error"],
                    }
                    (records / (each_key + study.JSON_EXTENSION)).write_text(json.dumps(receipt_record, indent=study.JSON_INDENT))
                    status_stream.write(f"{each_key} {receipt_record['state_pass']}\n")
                    status_stream.flush()
            if action == "quit":
                break



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("records", type=Path)
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=study.REPETITIONS)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    args = parser.parse_args()
    serve(args.baseline, args.candidate, args.work, args.records, args.repeats, args.cases)
