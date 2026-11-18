"""Run one or both installed prompt versions against fresh local workspaces."""

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from install import digest, verify_input
from receiver import Receiver

HERE = Path(__file__).resolve().parent
REVIEW = HERE.parents[1] / "packages/claude-dev-env/.agents/skills/build-eval/evals/review"
sys.path.insert(0, str(REVIEW))
from review_eval_support.account import CodexAccountUnavailable, codex_environment


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def capture(command, root, environment, prompt, seconds, private):
    started = time.monotonic()
    with (private / "stream.jsonl").open("w") as stream, (private / "stderr.txt").open("w") as log:
        process = subprocess.Popen(
            command, cwd=root, env=environment, stdin=subprocess.PIPE, stdout=stream,
            stderr=log, start_new_session=True, text=True,
        )
        timeout = False
        try:
            process.communicate(prompt, timeout=seconds)
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    elapsed = round(time.monotonic() - started, 2)
    stream_text = (private / "stream.jsonl").read_bytes().decode(errors="replace")
    lines = stream_text.splitlines(keepends=True)
    events = []
    malformed = False
    for line in lines:
        if line.strip():
            try:
                events.append(json.loads(line))
            except ValueError:
                malformed = True
    completed = [event for event in events if event.get("type") == "turn.completed"]
    items = [e.get("item", {}) for e in events if e.get("type") == "item.completed"]
    replies = [item.get("text") for item in items if item.get("type") == "agent_message"]
    status = "finished" if process.returncode == 0 and not malformed and len(completed) == 1 and replies else "launcher_error"
    if timeout:
        status = "timeout"
    return {
        "status": status, "exit": process.returncode, "seconds": elapsed,
        "usage": completed[-1].get("usage") if completed else None,
        "commands": sum(item.get("type") == "command_execution" for item in items),
        "turns": len(completed), "malformed_stream": malformed, "final": replies[-1] if replies else "",
    }


def run_one(case, settings, arm, home, number, environment, version):
    private = settings.results / arm / case["id"] / str(number)
    private.mkdir(parents=True)
    metadata = json.loads((home / "install.json").read_text())
    installed_prompt = home / ".codex/codex-sol.md"
    if digest(installed_prompt.read_bytes()) != metadata["prompt_sha256"]:
        raise ValueError("Installed prompt changed since rendering")
    overrides = ["-c", "model_instructions_file=" + json.dumps(str(installed_prompt))]
    command = [
        "codex", *overrides, "exec", "--model", settings.model, "-c",
        'model_reasoning_effort="high"', "--sandbox", "workspace-write", "-c",
        'approval_policy="never"', "--ephemeral", "--skip-git-repo-check", "--json", "-",
    ]
    with tempfile.TemporaryDirectory(prefix="receiving-") as scratch:
        root = Path(scratch)
        verify_input(environment, installed_prompt, root, overrides)
        with Receiver(root, case) as receiver:
            run = capture(command, root, environment, case["prompt"], settings.seconds, private)
        state = receiver.score()
        shutil.copytree(root, private / "work", symlinks=True)
    if state["receiver_error"]:
        run["status"] = "receiver_error"
    result = {
        **metadata, "arm": arm, "case": case["id"], "repeat": number, "split": case["split"],
        "codex": version, "model": settings.model, "effort": "high", "budget_seconds": settings.seconds,
        "dataset": digest((HERE / "cases.json").read_bytes()), "blind_id": secrets.token_hex(8),
        **run, **state,
    }
    result["state_pass"] = run["status"] == "finished" and state["receipt_goal"] and not state["violations"]
    write_json(private / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6.2-sol")
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=2)
    parser.add_argument("--seconds", type=int, choices=range(30, 601), default=180, metavar="30..600")
    parser.add_argument("--split", choices=["development", "held-out", "all"], default="all")
    settings = parser.parse_args()
    if os.name != "posix":
        parser.error("Use a Linux eval sandbox")
    settings.results = settings.results.resolve()
    settings.results.mkdir(parents=True, exist_ok=False)
    settings.results.chmod(0o700)
    cases = json.loads((HERE / "cases.json").read_text())
    selected = [c for c in cases if settings.split in {"all", c["split"]}]
    arms = [("baseline", settings.baseline.resolve())]
    if settings.candidate:
        arms.append(("candidate", settings.candidate.resolve()))
        hashes = {json.loads((home / "install.json").read_text())["prompt_sha256"] for _, home in arms}
        if len(hashes) != 2:
            parser.error("The two installed prompts are identical")
    if not os.environ.get("CODEX_HOME", "").strip():
        parser.error("Set CODEX_HOME to the provisioned eval account")
    write_json(settings.results / "manifest.json", {
        "cases": [c["id"] for c in selected], "repeats": settings.repeats,
        "arms": [arm for arm, _ in arms], "split": settings.split,
        "model": settings.model, "effort": "high", "seconds": settings.seconds,
        "harness": {name: digest((HERE / name).read_bytes()) for name in (
            "cases.json", "desk.py", "receiver.py", "run.py", "install.py", "report.py",
        )},
    })
    try:
        environment = codex_environment()
    except CodexAccountUnavailable as error:
        write_json(settings.results / "blocked.json", {"status": "account_unavailable", "reason": str(error)})
        parser.exit(3, str(error) + "\n")
    if Path(environment["CODEX_HOME"]).resolve() != Path(os.environ["CODEX_HOME"]).resolve():
        parser.exit(3, "Use the configured eval account home for every arm.\n")
    version = subprocess.check_output(["codex", "--version"], text=True).strip()
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_PAT"):
        environment.pop(key, None)
    results = []
    for number in range(1, settings.repeats + 1):
        for index, case in enumerate(selected):
            for arm, home in (arms if (number + index) % 2 else reversed(arms)):
                result = run_one(case, settings, arm, home, number, environment, version)
                results.append(result)
                print(arm, case["id"], number, result["status"], result["state_pass"], flush=True)
                if result["status"] in {"launcher_error", "receiver_error"}:
                    parser.exit(2, "Infrastructure failure. See the private capture.\n")
    case_by_id = {c["id"]: c for c in cases}
    blind = [{
        "id": r["blind_id"], "case": r["case"], "contract": case_by_id[r["case"]],
        "final": r["final"], "receipts": r["receipts"], "events": r["desk_events"], "changes": r["protected_changes"],
        "status": r["status"], "commands": r["commands"], "violations": r["violations"],
    } for r in results]
    secrets.SystemRandom().shuffle(blind)
    write_json(settings.results / "blind.json", blind)


if __name__ == "__main__":
    main()
