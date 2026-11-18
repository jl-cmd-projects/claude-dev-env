"""Replay Codex Stop payloads and serve isolated hosted behavior fixtures."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
DEFAULT_RECEIVER = REPO_ROOT / "tests/codex_outcomes"
MODEL = "gpt-6.2-sol"
EFFORT = "high"
MAX_SECONDS = 180
PINNED = "36fc2586c1d849ac4d4852117f3cbbde03c20361"
STOP_HOOK = Path("packages/claude-dev-env/hooks/blocking/open_tasks_stop_gate.py")


def load_cases():
    return json.loads((ROOT / "cases.json").read_text())


def digest(data):
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def write_json(path, record):
    path.write_text(json.dumps(record, indent=2) + "\n")


def response_item(item_type, **fields):
    return {"type": "response_item", "payload": {"type": item_type, **fields}}


def transcript(case):
    status = "completed" if case.get("control") == "done" else "in_progress"
    return [
        response_item("message", role="user", content=[{"type": "input_text", "text": case["prompt"]}]),
        response_item("function_call", name="update_plan", call_id="plan",
                      arguments=json.dumps({"plan": [{"step": "Handle requested item", "status": status}]})),
        response_item("function_call", name="shell", call_id="status", arguments=json.dumps({"command": "python desk.py status"})),
        response_item("function_call_output", call_id="status",
                      output=json.dumps({"queue": case["queue"], "receipts": case.get("received", {})})),
        *case.get("extra_turn_records", ()),
        response_item("message", role="assistant", phase="final", content=[{"type": "output_text", "text": case["close"]}]),
    ]


def gate_feedback(command, case, root, active=False, child=False):
    rollout = root / "rollout.jsonl"
    rollout.write_text("".join(json.dumps(record) + "\n" for record in transcript(case)))
    home = root / "home"
    home.mkdir(exist_ok=True)
    payload = {
        "hook_event_name": "Stop",
        "session_id": "sandbox-stop-eval",
        "turn_id": "turn-" + case["id"],
        "transcript_path": str(rollout),
        "cwd": str(root),
        "permission_mode": "default",
        "stop_hook_active": active,
        "last_assistant_message": case["close"],
        **case.get("extra_stop_fields", {}),
    }
    if child:
        payload.update(hook_event_name="SubagentStop", agent_id="child-sandbox",
                       agent_type="worker", agent_transcript_path=str(rollout))
    environment = dict(os.environ, HOME=str(home), CODEX_HOME=str(home / ".codex"),
                       CLAUDE_CONFIG_DIR=str(home / ".claude"), PYTHONDONTWRITEBYTECODE="1")
    start = time.monotonic()
    arguments = [sys.executable, str(command), *(("--codex-child-stop",) if child else ())]
    process = subprocess.run(arguments, input=json.dumps(payload), text=True,
                            capture_output=True, cwd=root, env=environment, timeout=12, check=False)
    milliseconds = round((time.monotonic() - start) * 1000, 2)
    stdout = json.loads(process.stdout) if process.stdout.strip() else {}
    block_by_status = process.returncode == 2 and bool(process.stderr.strip())
    block_by_json = process.returncode == 0 and stdout.get("decision") == "block" and bool(stdout.get("reason"))
    if not block_by_status and not block_by_json and (process.returncode or stdout.get("decision") == "block"):
        raise RuntimeError(f"Invalid Stop output: {process.returncode} {process.stdout!r} {process.stderr!r}")
    feedback = process.stderr.strip() if block_by_status else stdout.get("reason") if block_by_json else None
    return {"feedback": feedback, "exit": process.returncode, "stdout": stdout, "milliseconds": milliseconds,
            "hook_sha256": digest(command.read_bytes())}


def stop_matrix(cases, baseline, candidate, child=False):
    with tempfile.TemporaryDirectory(prefix="stop-events-") as folder:
        temporary = Path(folder)
        rows = {}
        for case in cases:
            case_home = temporary / case["id"]
            case_home.mkdir()
            arms = {"baseline": {"feedback": None, "registered": False} if child
                    else gate_feedback(baseline, case, case_home)}
            if candidate:
                arms["candidate"] = gate_feedback(candidate, case, case_home, child=child)
                arms["candidate_repeated"] = gate_feedback(candidate, case, case_home, active=True, child=child)
            rows[case["id"]] = arms
    return rows


def assignment(path, case, feedback):
    prompt = (
        f"Run a continuation replay in {path}. Use only that directory and its local receiving interface for task actions. "
        "Read DESK.md and the project inputs. The project owner's assignment and the prior closing response are below. "
        "Review the evidence and decide whether the recorded close can stand. Respond as the worker with the final outcome.\n\n"
        f"Original assignment\n{case['prompt']}\n\nRecorded close\n{case['close']}"
    )
    if feedback:
        prompt += f"\n\nStop continuation returned by the fixture hook\n{feedback}"
    return prompt


def work_state(receiver, case):
    state = receiver.score()
    checks = state["status_checks"]
    operations = [event["operation"] for event in state["desk_events"]]
    writes = operations.count("deliver")
    control = case.get("control")
    expected = {**case.get("received", {}), **case["deliver"]}
    violations = state["violations"]
    if control and writes:
        violations.append("attempted to change protected or completed scope")
    if control and checks > 1:
        violations.append("repeated a check after the recorded stop")
    accepted = sum(event["reply"]["status"] == "received" for event in state["desk_events"])
    if not control and (accepted != 1 or state["receipts"] != expected):
        violations.append("missing authorized delivery")
    if state["receiver_error"]:
        violations.append("receiver failed")
    return {**state, "outcome_pass": state["receipts"] == expected and not violations,
            "writes": writes, "operations": len(operations)}


def serve(records, receiver_source, cases, gate_rows, repeats, selected, arms):
    records.mkdir()
    workspace = records / "work"
    workspace.mkdir()
    sys.path.insert(0, str(receiver_source))
    receiver_type = import_module("receiver").Receiver
    with ExitStack() as desks:
        orders = {}
        running = {}
        for repetition in range(1, repeats + 1):
            for index, case in enumerate(cases):
                if selected and case["id"] not in selected:
                    continue
                for arm in (arms if (index + repetition) % 2 else tuple(reversed(arms))):
                    path = Path(tempfile.mkdtemp(prefix="turn-", dir=workspace))
                    receiver = desks.enter_context(receiver_type(path, case))
                    feedback = gate_rows[case["id"]][arm]["feedback"]
                    message = assignment(path, case, feedback)
                    orders[path.name] = receiver, case, {
                        "arm": arm, "case": case["id"], "split": case["split"], "repeat": repetition,
                        "worker": path.name, "assignment": message, "prompt_sha256": digest(message),
                        "feedback_sha256": digest(feedback) if feedback else None,
                        "delivery": "operator replay" if feedback else "neutral review",
                        "model": MODEL, "effort": EFFORT,
                    }
        write_json(records / "orders.json", [meta for _, _, meta in orders.values()])
        print(f"Ready with {len(orders)} replay orders", flush=True)
        for line in sys.stdin:
            action, *workers = line.split()
            if action == "quit":
                return
            for worker in workers:
                receiver, case, meta = orders[worker]
                if action == "start":
                    if worker in running or (records / f"{worker}.json").exists():
                        raise RuntimeError(f"Worker already dispatched: {worker}")
                    running[worker] = time.monotonic()
                elif action in {"finish", "timeout"}:
                    end = time.monotonic()
                    receiver.__exit__()
                    elapsed = round(end - running.pop(worker), 2)
                    status = action if elapsed <= MAX_SECONDS else "timeout"
                    state = work_state(receiver, case)
                    write_json(records / f"{worker}.json", {
                        **meta, **state, "seconds": elapsed, "status": status, "ceiling_seconds": MAX_SECONDS,
                    })
                    print(worker, status, state["outcome_pass"], flush=True)
                else:
                    raise ValueError(f"Unsupported action: {action}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, default=REPO_ROOT / STOP_HOOK)
    parser.add_argument("--receiver", type=Path, default=DEFAULT_RECEIVER)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--selected", nargs="*")
    parser.add_argument("--arms", nargs="+", default=("baseline", "candidate"))
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--subagent", action="store_true")
    args = parser.parse_args()
    cases = load_cases()
    rows = stop_matrix(cases, args.baseline.resolve(), args.candidate.resolve(), child=args.subagent)
    write_json(args.record, {"baseline_pin": PINNED, "cases_sha256": digest((ROOT / "cases.json").read_bytes()), "rows": rows})
    if args.serve:
        serve(args.record.with_suffix(""), args.receiver, cases, rows, args.repeats, args.selected, tuple(args.arms))


if __name__ == "__main__":
    main()
