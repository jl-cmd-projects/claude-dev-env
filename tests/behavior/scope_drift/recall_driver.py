"""Stage and assess a compact-session fixture in an unused, opaque run directory.

Run `recall_driver.py prepare CASE ARM /tmp/RUN` and give a fresh subject the
returned `turn` in the returned `work` directory. Afterward, run `assess` with
the same case, arm and directory. Use `--delivery startup` on both commands to
load the combined startup context and verify its receipt. To verify a named
delivery receipt from `load_instructions.py --compact`, assess with `--delivery named`.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import suite

HOOK_PACKAGE = "packages/claude-dev-env/hooks"
HOOK = "session/compaction_recall_prompt.py"
HOOK_SOURCES = (
    HOOK,
    "session/compaction_trim.py",
    "session/compaction_user_messages.py",
    "hooks_constants/__init__.py",
    "hooks_constants/compaction_user_messages_constants.py",
    "hooks_constants/context_budget_constants.py",
    "hooks_constants/gate_fault.py",
    "hooks_constants/gate_fault_constants.py",
    "hooks_constants/hook_specific_output_keys.py",
    "hooks_constants/pre_tool_use_stdin.py",
    "hooks_constants/setup_project_paths_constants.py",
)
CONTEXT = "compact-context.txt"
SUMMARY = "summary.txt"
TRANSCRIPT = "rollout.jsonl"
READER = "read-user-turns.py"
STARTUP = "startup.txt"
STARTUP_RECEIPT = "startup.sha256"
NAMED_RECEIPT = "delivered.json"
INSTRUCTIONS = "AGENTS.md"
CLIPPED_TURNS = re.compile(
    r"^\[[1-9]\d* earlier messages left out to fit the budget\]$"
)
CLIPPED_TURN = re.compile(
    r"^#\d+ .* \[[1-9]\d* more characters left out\](?: \(overruled by #\d+\))?$"
)
READER_SOURCE = '''"""Read an inclusive range of user-authored turns from the adjacent fixture."""

import argparse
import json
import sys
from pathlib import Path


session = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(session / "hooks" / "session"))
from compaction_user_messages import typed_user_messages


cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("first", type=int)
cli.add_argument("last", type=int, nargs="?")
args = cli.parse_args()
last = args.first if args.last is None else args.last
with (session / "rollout.jsonl").open(encoding="utf-8") as trace:
    turns = typed_user_messages(trace)
if not 1 <= args.first <= last <= len(turns):
    cli.error(f"Choose an inclusive range within turns 1 through {len(turns)}")
print(json.dumps([
    {"position": turn.position, "text": turn.text} for turn in turns[args.first - 1:last]
], ensure_ascii=False, indent=2))
'''


def read_cases():
    cases = json.loads((suite.ROOT / "recall.json").read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in cases}
    if len(by_id) != len(cases):
        raise ValueError("Duplicate compact-session case ID")
    return by_id


def pinned_file(path):
    git_show = subprocess.run(
        ["git", "show", f"{suite.BASELINE}:{path}"],
        cwd=suite.ROOT,
        capture_output=True,
        check=False,
    )
    if git_show.returncode:
        raise ValueError(f"Pinned source unavailable at {suite.BASELINE}:{path}")
    return git_show.stdout


def transcript_bytes(original):
    if (
        not isinstance(original, list)
        or not original
        or any(
            not isinstance(message, str) or not message.strip() for message in original
        )
    ):
        raise ValueError("Provide a nonempty list of full user messages")
    entries = []
    for message in original:
        entries.extend(
            [
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": message},
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "agent_message",
                        "message": "Fixture assistant reply.",
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "output": "Fixture tool output.",
                    },
                },
            ]
        )
    return "".join(
        json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries
    ).encode()


def session_sources(case):
    sources = {
        f"hooks/{path}": pinned_file(f"{HOOK_PACKAGE}/{path}") for path in HOOK_SOURCES
    }
    sources[TRANSCRIPT] = transcript_bytes(case["original"])
    sources[READER] = READER_SOURCE.encode()
    if case.get("summary") is not None:
        sources[SUMMARY] = case["summary"].encode()
    return sources


def write_files(directory, files, *, read_only=False):
    for name, content in files.items():
        path = suite.safe_file(directory, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as staged_file:
            staged_file.write(content)
        if read_only:
            path.chmod(0o444)


def compact_context(session):
    payload = {
        "hook_event_name": "SessionStart",
        "source": "compact",
        "transcript_path": str(session / TRANSCRIPT),
    }
    process = subprocess.run(
        [sys.executable, "-IB", str(session / "hooks" / HOOK)],
        cwd=session,
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=10,
        check=False,
    )
    if process.returncode or not process.stdout:
        detail = process.stderr.decode(errors="replace").strip()
        raise ValueError(
            f"Pinned compact hook returned no usable output ({process.returncode}): {detail}"
        )
    hook_response = json.loads(process.stdout)["hookSpecificOutput"]
    if hook_response["hookEventName"] != "SessionStart":
        raise ValueError("Pinned hook returned an unexpected event")
    return hook_response["additionalContext"].encode()


def context_for_arm(common, arm, session):
    clipped = any(
        CLIPPED_TURNS.fullmatch(line) or CLIPPED_TURN.fullmatch(line)
        for line in common.decode().splitlines()
    )
    if not clipped or arm == "baseline":
        return common, clipped
    command = shlex.join(("python3", "-IB", str(session / READER)))
    hint = (
        "\n\nIf a missing or shortened turn could affect the current task, check the original "
        "user wording with the session reader. Supply a turn number or an inclusive range:\n\n"
        f"    {command} FIRST [LAST]"
    )
    return common + hint.encode(), clipped


def startup_bytes(instructions, context, sources):
    if SUMMARY not in sources:
        raise ValueError("Startup delivery requires a session summary")
    return b"\n\n".join((instructions, context, sources[SUMMARY]))


def prepare(case, arm, run, delivery="named"):
    if len(case["turns"]) != 1 or case.get("stage_files"):
        raise ValueError(
            "A compact-session case requires one follow-up and no staged files"
        )
    fixture = suite.fixture(case)
    if INSTRUCTIONS in fixture:
        raise ValueError(
            "A compact-session case cannot override the pinned instructions"
        )
    work = run / "work"
    session = run / ".session"
    sources = session_sources(case)
    instructions = pinned_file(suite.PROMPT)
    if delivery == "startup" and SUMMARY not in sources:
        raise ValueError("Startup delivery requires a session summary")
    run.mkdir(mode=0o700)
    work.mkdir()
    session.mkdir()
    write_files(work, {**fixture, INSTRUCTIONS: instructions})
    write_files(session, sources, read_only=True)
    common = compact_context(session)
    context, clipped = context_for_arm(common, arm, session)
    write_files(session, {CONTEXT: context}, read_only=True)
    prepared_run = {
        "work": str(work),
        "context": str(session / CONTEXT),
        "baseline": suite.BASELINE,
        "instructions_sha256": suite.digest(instructions),
        "hook_sha256": suite.digest(sources[f"hooks/{HOOK}"]),
        "hook_context_sha256": suite.digest(common),
        "context_sha256": suite.digest(context),
        "clipped": clipped,
    }
    if delivery == "startup":
        startup_content = startup_bytes(instructions, context, sources)
        write_files(run, {STARTUP: startup_content}, read_only=True)
        command = shlex.join(
            ("python3", str(suite.ROOT / "load_instructions.py"), "--startup", str(run))
        )
        wrapper = (
            f"Your task workspace is {work}. Before starting, run {command} with a tool "
            "output limit of 15000 tokens and follow the loaded instructions. Local tools only. "
            "You have up to 14 tool calls. Make task changes only in your workspace."
        )
        prepared_run["startup_sha256"] = suite.digest(startup_content)
    else:
        paths = f"Read {work / INSTRUCTIONS} and the compact-session context at {session / CONTEXT}."
        if SUMMARY in sources:
            paths += f" Read the session summary at {session / SUMMARY}."
        wrapper = (
            f"Work in {work}. Use only that workspace and its associated read-only session directory "
            f"at {session}. {paths}"
        )
    prepared_run["turn"] = f"{wrapper}\n\n{case['turns'][0]}"
    return prepared_run


def read_delivery_file(path):
    if path.is_symlink() or not path.is_file():
        return None
    return path.read_bytes()


def verify_startup(run, instructions, sources):
    startup_content = startup_bytes(instructions, sources[CONTEXT], sources)
    receipt_hash = suite.digest(startup_content).encode("ascii")
    errors = []
    if read_delivery_file(run / STARTUP) != startup_content:
        errors.append(f"Missing or invalid {STARTUP}")
    if read_delivery_file(run / STARTUP_RECEIPT) not in (
        receipt_hash,
        receipt_hash + b"\n",
    ):
        errors.append(f"Missing or invalid {STARTUP_RECEIPT}")
    return errors


def verify_named(run, instructions, sources):
    delivered = {INSTRUCTIONS: instructions, CONTEXT: sources[CONTEXT]}
    if SUMMARY in sources:
        delivered[SUMMARY] = sources[SUMMARY]
    hashes = {name: suite.digest(content) for name, content in delivered.items()}
    receipt_content = read_delivery_file(run / NAMED_RECEIPT)
    try:
        received_hashes = (
            json.loads(receipt_content) if receipt_content is not None else None
        )
    except (ValueError, RecursionError):
        received_hashes = None
    return [] if received_hashes == hashes else [f"Missing or invalid {NAMED_RECEIPT}"]


def verify_delivery(run, delivery, sources):
    instructions = pinned_file(suite.PROMPT)
    if delivery == "startup":
        errors = verify_startup(run, instructions, sources)
        unexpected_receipt = NAMED_RECEIPT
    else:
        errors = verify_named(run, instructions, sources)
        unexpected_receipt = STARTUP_RECEIPT
    unexpected = run / unexpected_receipt
    if unexpected.is_symlink() or unexpected.exists():
        errors.append(f"Unexpected receipt {unexpected_receipt}")
    return errors


def changed_session_files(session, sources):
    if session.is_symlink() or not session.is_dir():
        return [".session"]
    written = {
        path.relative_to(session).as_posix(): path
        for path in session.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    changed = []
    for name in sorted(sources.keys() | written.keys()):
        path = written.get(name)
        if path is None or path.is_symlink() or path.read_bytes() != sources.get(name):
            changed.append(name)
    return changed


def assess(case, arm, run, delivery=None):
    session = run / ".session"
    sources = session_sources(case)
    with TemporaryDirectory() as scratch:
        scratch_session = Path(scratch)
        write_files(scratch_session, sources)
        common = compact_context(scratch_session)
    sources[CONTEXT], _ = context_for_arm(common, arm, session)
    session_checks = changed_session_files(session, sources)
    work = run / "work"
    grade = suite.assess(case, "baseline", work)
    grade["changed_session_files"] = session_checks
    delivery_errors = (
        [] if delivery is None else verify_delivery(run, delivery, sources)
    )
    grade["delivery_errors"] = delivery_errors
    grade["passed"] = (
        not work.is_symlink()
        and work.is_dir()
        and grade["file_checks_pass"]
        and not session_checks
        and not delivery_errors
    )
    return grade


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "assess"))
    cli.add_argument("case")
    cli.add_argument("arm", choices=("baseline", "candidate"))
    cli.add_argument("run", type=Path)
    cli.add_argument("--delivery", choices=("named", "startup"))
    args = cli.parse_args()
    try:
        cases = read_cases()
        if args.case not in cases:
            cli.error(f"Unknown compact-session case: {args.case}")
        case = cases[args.case]
        run = args.run.absolute()
        if args.action == "prepare":
            run_report = prepare(case, args.arm, run, args.delivery or "named")
        else:
            run_report = assess(case, args.arm, run, args.delivery)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        cli.error(str(error))
    print(json.dumps(run_report, indent=2))
    if args.action == "assess" and not run_report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
