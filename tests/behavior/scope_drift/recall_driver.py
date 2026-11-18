"""Stage and assess a compact-session fixture in an unused, opaque run directory.

Run `recall_driver.py prepare CASE ARM /tmp/RUN` and give a fresh subject the
returned `turn` in the returned `work` directory. Afterward, run `assess` with
the same case, arm and directory. Use `--delivery startup` on both commands to
load the combined startup context and verify its receipt. To verify a named
delivery receipt from `load_instructions.py --compact`, assess with `--delivery named`.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory
from typing import NotRequired, TextIO

if __package__:
    from . import suite
    from .config import recall as protocol
else:
    import suite

    from config import recall as protocol


class RecallRunFatal(ValueError):
    """Raised when a recall trial cannot be prepared or checked."""


class RecallCase(suite.ScopeCase):
    """Scope case with the full turns that precede compaction."""

    original: list[str]
    summary: NotRequired[str]


class RecallGrade(suite.FileGrade):
    """Workspace grade with session integrity and receipt checks."""

    changed_session_files: list[str]
    delivery_errors: list[str]
    passed: bool


def read_cases() -> dict[str, RecallCase]:
    """Read the archived compact-session cases.

    Returns:
        Cases indexed by case ID.

    Raises:
        RecallRunFatal: If two cases share an ID.
    """
    cases = json.loads((suite.ROOT / "recall.json").read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in cases}
    if len(by_id) != len(cases):
        raise RecallRunFatal("Duplicate compact-session case ID")
    return by_id


def _pinned_file(path: str) -> bytes:
    git_show = subprocess.run(
        ["git", "show", f"{suite.BASELINE}:{path}"],
        cwd=suite.ROOT,
        capture_output=True,
        check=False,
    )
    if git_show.returncode:
        raise RecallRunFatal(f"Pinned source unavailable at {suite.BASELINE}:{path}")
    return git_show.stdout


def _transcript_bytes(original: object) -> bytes:
    if (
        not isinstance(original, list)
        or not original
        or any(
            not isinstance(message, str) or not message.strip() for message in original
        )
    ):
        raise RecallRunFatal("Provide a nonempty list of full user messages")
    entries = []
    for each_message in original:
        entries.extend(
            [
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": each_message},
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


def _session_sources(case: RecallCase) -> dict[str, bytes]:
    all_sources = {
        f"hooks/{path}": _pinned_file(f"{protocol.HOOK_PACKAGE}/{path}")
        for path in protocol.ALL_HOOK_SOURCES
    }
    all_sources[protocol.TRANSCRIPT] = _transcript_bytes(case["original"])
    all_sources[protocol.READER] = protocol.READER_SOURCE.encode()
    if case.get("summary") is not None:
        all_sources[protocol.SUMMARY] = case["summary"].encode()
    return all_sources


def _write_files(
    directory: Path, all_files: dict[str, bytes], *, should_make_read_only: bool
) -> None:
    for each_name, each_content in all_files.items():
        path = suite.safe_file(directory, each_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as staged_file:
            staged_file.write(each_content)
        if should_make_read_only:
            path.chmod(0o444)


def _compact_context(session: Path) -> bytes:
    payload = {
        "hook_event_name": "SessionStart",
        "source": "compact",
        "transcript_path": str(session / protocol.TRANSCRIPT),
    }
    process = subprocess.run(
        [sys.executable, "-IB", str(session / "hooks" / protocol.HOOK)],
        cwd=session,
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=protocol.HOOK_TIMEOUT_SECONDS,
        check=False,
    )
    if process.returncode or not process.stdout:
        detail = process.stderr.decode(errors="replace").strip()
        raise RecallRunFatal(
            f"Pinned compact hook returned no usable output ({process.returncode}): {detail}"
        )
    hook_fields = json.loads(process.stdout)["hookSpecificOutput"]
    if hook_fields["hookEventName"] != "SessionStart":
        raise RecallRunFatal("Pinned hook returned an unexpected event")
    return hook_fields["additionalContext"].encode()


def context_for_arm(common: bytes, arm: str, session: PurePath) -> tuple[bytes, bool]:
    """Add the study's recovery reference when the pinned hook clips a turn.

    Args:
        common: The unmodified hook context shared by both arms.
        arm: The baseline or candidate arm.
        session: Path to the associated synthetic session.

    Returns:
        The delivered context and whether the hook clipped a turn.
    """
    clipped = any(
        protocol.CLIPPED_TURNS.fullmatch(line) or protocol.CLIPPED_TURN.fullmatch(line)
        for line in common.decode().splitlines()
    )
    if not clipped or arm == protocol.BASELINE_ARM:
        return common, clipped
    command = shlex.join(("python3", "-IB", str(session / protocol.READER)))
    hint = (
        "\n\nIf a missing or shortened turn could affect the current task, check the original "
        "user wording with the session reader. Supply a turn number or an inclusive range:\n\n"
        f"    {command} FIRST [LAST]"
    )
    return common + hint.encode(), clipped


def _startup_bytes(
    instructions: bytes, context: bytes, all_sources: dict[str, bytes]
) -> bytes:
    if protocol.SUMMARY not in all_sources:
        raise RecallRunFatal("Startup delivery requires a session summary")
    return b"\n\n".join((instructions, context, all_sources[protocol.SUMMARY]))


def prepare(
    case: RecallCase,
    arm: str,
    run: Path,
    delivery: str = protocol.NAMED_DELIVERY,
) -> dict[str, str | bool]:
    """Stage a fresh workspace and its compact-session sources.

    Args:
        case: Fixture with the full pre-compaction turns and the follow-up.
        arm: The baseline or candidate arm.
        run: A new directory for the workspace and session archive.
        delivery: The named archive or startup stream mode.

    Returns:
        Workspace and context paths, input hashes, and the subject's first turn.

    Raises:
        RecallRunFatal: If the case or pinned sources cannot stage a trial.
    """
    if len(case["turns"]) != 1 or case.get("stage_files"):
        raise RecallRunFatal(
            "A compact-session case requires one follow-up and no staged files"
        )
    fixture = suite.fixture(case)
    if protocol.INSTRUCTIONS in fixture:
        raise RecallRunFatal(
            "A compact-session case cannot override the pinned instructions"
        )
    work = run / "work"
    session = run / protocol.SESSION
    all_sources = _session_sources(case)
    instructions = _pinned_file(suite.PROMPT)
    if delivery == protocol.STARTUP_DELIVERY and protocol.SUMMARY not in all_sources:
        raise RecallRunFatal("Startup delivery requires a session summary")
    run.mkdir(mode=0o700)
    work.mkdir()
    session.mkdir()
    _write_files(
        work,
        {**fixture, protocol.INSTRUCTIONS: instructions},
        should_make_read_only=False,
    )
    _write_files(session, all_sources, should_make_read_only=True)
    common = _compact_context(session)
    context, clipped = context_for_arm(common, arm, session)
    _write_files(session, {protocol.CONTEXT: context}, should_make_read_only=True)
    prepared_run: dict[str, str | bool] = {
        "work": str(work),
        "context": str(session / protocol.CONTEXT),
        "baseline": suite.BASELINE,
        "instructions_sha256": suite.digest(instructions),
        "hook_sha256": suite.digest(all_sources[f"hooks/{protocol.HOOK}"]),
        "hook_context_sha256": suite.digest(common),
        "context_sha256": suite.digest(context),
        "clipped": clipped,
    }
    if delivery == protocol.STARTUP_DELIVERY:
        startup_content = _startup_bytes(instructions, context, all_sources)
        _write_files(
            run, {protocol.STARTUP: startup_content}, should_make_read_only=True
        )
        prepared_run["startup_sha256"] = suite.digest(startup_content)
    wrapper = _delivery_wrapper(run, work, session, delivery)
    prepared_run["turn"] = f"{wrapper}\n\n{case['turns'][0]}"
    return prepared_run


def _delivery_wrapper(run: Path, work: Path, session: Path, delivery: str) -> str:
    if delivery == protocol.STARTUP_DELIVERY:
        command = shlex.join(
            ("python3", str(suite.ROOT / "load_instructions.py"), "--startup", str(run))
        )
        return (
            f"Your task workspace is {work}. Before starting, run {command} with a tool "
            "output limit of 15000 tokens and follow the loaded instructions. Local tools only. "
            "You have up to 14 tool calls. Make task changes only in your workspace."
        )
    command = shlex.join(
        ("python3", str(suite.ROOT / "load_instructions.py"), "--compact", str(run))
    )
    return (
        f"Work in {work}. The associated read-only session archive is {session}. "
        f"Before starting, run {command} with a tool output limit of 15000 tokens "
        "and follow the loaded instructions. Local tools only. You have up to "
        "14 tool calls. Make task changes only in your workspace."
    )


def _read_delivery_file(path: Path) -> bytes | None:
    if path.is_symlink() or not path.is_file():
        return None
    return path.read_bytes()


def _verify_startup(
    run: Path, instructions: bytes, all_sources: dict[str, bytes]
) -> list[str]:
    startup_content = _startup_bytes(
        instructions, all_sources[protocol.CONTEXT], all_sources
    )
    receipt_hash = suite.digest(startup_content).encode("ascii")
    errors = []
    if _read_delivery_file(run / protocol.STARTUP) != startup_content:
        errors.append(f"Missing or invalid {protocol.STARTUP}")
    if _read_delivery_file(run / protocol.STARTUP_RECEIPT) not in (
        receipt_hash,
        receipt_hash + b"\n",
    ):
        errors.append(f"Missing or invalid {protocol.STARTUP_RECEIPT}")
    return errors


def _verify_named(
    run: Path, instructions: bytes, all_sources: dict[str, bytes]
) -> list[str]:
    delivered = {
        protocol.INSTRUCTIONS: instructions,
        protocol.CONTEXT: all_sources[protocol.CONTEXT],
    }
    if protocol.SUMMARY in all_sources:
        delivered[protocol.SUMMARY] = all_sources[protocol.SUMMARY]
    hashes = {name: suite.digest(content) for name, content in delivered.items()}
    receipt_content = _read_delivery_file(run / protocol.NAMED_RECEIPT)
    try:
        received_hashes = (
            json.loads(receipt_content) if receipt_content is not None else None
        )
    except (ValueError, RecursionError):
        received_hashes = None
    return (
        []
        if received_hashes == hashes
        else [f"Missing or invalid {protocol.NAMED_RECEIPT}"]
    )


def _verify_delivery(
    run: Path, delivery: str, all_sources: dict[str, bytes]
) -> list[str]:
    instructions = _pinned_file(suite.PROMPT)
    if delivery == protocol.STARTUP_DELIVERY:
        errors = _verify_startup(run, instructions, all_sources)
        unexpected_receipt = protocol.NAMED_RECEIPT
    else:
        errors = _verify_named(run, instructions, all_sources)
        unexpected_receipt = protocol.STARTUP_RECEIPT
    unexpected = run / unexpected_receipt
    if unexpected.is_symlink() or unexpected.exists():
        errors.append(f"Unexpected receipt {unexpected_receipt}")
    return errors


def _changed_session_files(session: Path, all_sources: dict[str, bytes]) -> list[str]:
    if session.is_symlink() or not session.is_dir():
        return [protocol.SESSION]
    written = {
        path.relative_to(session).as_posix(): path
        for path in session.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    changed = []
    for each_name in sorted(all_sources.keys() | written.keys()):
        path = written.get(each_name)
        if (
            path is None
            or path.is_symlink()
            or path.read_bytes() != all_sources.get(each_name)
        ):
            changed.append(each_name)
    return changed


def assess(
    case: RecallCase, arm: str, run: Path, delivery: str | None = None
) -> RecallGrade:
    """Grade a completed workspace and verify the session sources.

    Args:
        case: Fixture with the task oracle and full pre-compaction turns.
        arm: The baseline or candidate arm.
        run: Directory prepared for this trial.
        delivery: Receipt mode to verify, if the trial requires one.

    Returns:
        Workspace grade, source changes, receipt errors and the pass flag.
    """
    session = run / protocol.SESSION
    all_sources = _session_sources(case)
    with TemporaryDirectory() as scratch:
        scratch_session = Path(scratch)
        _write_files(scratch_session, all_sources, should_make_read_only=False)
        common = _compact_context(scratch_session)
    all_sources[protocol.CONTEXT], _ = context_for_arm(common, arm, session)
    session_checks = _changed_session_files(session, all_sources)
    work = run / "work"
    grade = suite.assess(case, protocol.BASELINE_ARM, work)
    delivery_errors = (
        [] if delivery is None else _verify_delivery(run, delivery, all_sources)
    )
    has_passed = (
        not work.is_symlink()
        and work.is_dir()
        and grade["file_checks_pass"]
        and not session_checks
        and not delivery_errors
    )
    return {
        **grade,
        "changed_session_files": session_checks,
        "delivery_errors": delivery_errors,
        "passed": has_passed,
    }


def _main(report_stream: TextIO) -> None:
    """Prepare or grade a single trial from command-line arguments.

    Args:
        report_stream: Destination for the JSON report.

    Raises:
        SystemExit: If arguments are invalid or grading reports a failure.
    """
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=(protocol.PREPARE, protocol.ASSESS))
    cli.add_argument("case")
    cli.add_argument("arm", choices=(protocol.BASELINE_ARM, protocol.CANDIDATE_ARM))
    cli.add_argument("run", type=Path)
    cli.add_argument(
        "--delivery", choices=(protocol.NAMED_DELIVERY, protocol.STARTUP_DELIVERY)
    )
    args = cli.parse_args()
    try:
        cases = read_cases()
        if args.case not in cases:
            cli.error(f"Unknown compact-session case: {args.case}")
        case = cases[args.case]
        run = args.run.absolute()
        run_report: dict[str, str | bool] | RecallGrade
        if args.action == protocol.PREPARE:
            run_report = prepare(
                case, args.arm, run, delivery=args.delivery or protocol.NAMED_DELIVERY
            )
        else:
            run_report = assess(case, args.arm, run, delivery=args.delivery)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        cli.error(str(error))
    json_indent = 2
    report_stream.write(json.dumps(run_report, indent=json_indent) + "\n")
    if args.action == protocol.ASSESS and not run_report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    _main(sys.stdout)
