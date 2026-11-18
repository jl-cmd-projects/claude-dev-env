"""Prepare a fresh working directory and compare its files to the case oracle."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import NotRequired, TextIO, TypedDict

if __package__:
    from .config.scope import (
        ALL_ACTIONS,
        ALL_ARMS,
        ALL_CASE_FILES,
        ANCHOR,
        BASELINE,
        BASELINE_ARM,
        JSON_INDENT,
        NEXT_TURN,
        PROMPT,
        ROOT,
    )
else:
    from config.scope import (
        ALL_ACTIONS,
        ALL_ARMS,
        ALL_CASE_FILES,
        ANCHOR,
        BASELINE,
        BASELINE_ARM,
        JSON_INDENT,
        NEXT_TURN,
        PROMPT,
        ROOT,
    )


class SuiteRunFatal(ValueError):
    """Invalid inputs prevent the scope evaluation from proceeding."""


class ScopeCase(TypedDict):
    """Operational inputs and grading criteria for a scope scenario."""

    id: str
    turns: list[str]
    files: dict[str, str | None]
    expect: dict[str, str]
    report: list[str]
    split: NotRequired[str]
    stage_files: NotRequired[list[dict[str, str]]]
    base: NotRequired[str]
    artifacts: NotRequired[dict[str, list[str]]]
    downstream: NotRequired[str]


class FileGrade(TypedDict):
    """Deterministic file comparisons and criteria for separate text review."""

    missing_or_wrong: list[str]
    unexpected: list[str]
    file_checks_pass: bool
    artifacts_to_read: dict[str, list[str]]
    final_to_verify: list[str]


def digest(contents: bytes) -> str:
    """Hash exact file contents for an input or artifact receipt.

    Args:
        contents: Bytes read from the prepared or captured file.

    Returns:
        The hexadecimal SHA-256 digest.
    """
    return hashlib.sha256(contents).hexdigest()


def _decode_scope_case(path: Path) -> list[ScopeCase]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_cases() -> dict[str, ScopeCase]:
    """Load the registered cases by their unique identifiers.

    Returns:
        A mapping from case identifier to fixture and grading criteria.

    Raises:
        SuiteRunFatal: A case identifier occurs more than once.
    """
    cases: dict[str, ScopeCase] = {}
    for each_name in ALL_CASE_FILES:
        for each_case in _decode_scope_case(ROOT / each_name):
            if each_case["id"] in cases:
                raise SuiteRunFatal(f"Duplicate case: {each_case['id']}")
            cases[each_case["id"]] = each_case
    return cases


def _encode_scope_case(
    case: ScopeCase, all_inherited_files: dict[str, str | None]
) -> dict[str, bytes]:
    return {
        path: contents.encode()
        for path, contents in (all_inherited_files | case["files"]).items()
        if contents is not None
    }


def fixture(case: ScopeCase) -> dict[str, bytes]:
    """Build the initial workspace files from the case and its optional base.

    Args:
        case: The fixture and case-specific file overrides.

    Returns:
        A mapping of workspace-relative paths to exact initial bytes.
    """
    files = (
        json.loads((ROOT / case["base"]).read_text(encoding="utf-8"))
        if "base" in case
        else {}
    )
    return _encode_scope_case(case, files)


def instructions(arm: str) -> bytes:
    """Load the pinned prompt and apply the experimental insertion if selected.

    Args:
        arm: The baseline or candidate instruction arm.

    Returns:
        The exact instruction bytes to install in the workspace.

    Raises:
        SuiteRunFatal: The pinned prompt has an ambiguous insertion point.
    """
    base = subprocess.check_output(["git", "show", f"{BASELINE}:{PROMPT}"], cwd=ROOT)
    if arm == BASELINE_ARM:
        return base
    if base.count(ANCHOR.encode()) != 1:
        raise SuiteRunFatal("Pinned insertion point must occur once")
    return base.replace(
        ANCHOR.encode(),
        ANCHOR.encode() + b"\n\n" + (ROOT / "candidate.txt").read_bytes().strip(),
    )


def safe_file(work: Path, name: str) -> Path:
    """Resolve a candidate path against the fixture boundary.

    Args:
        work: The workspace root allowed to contain the file.
        name: The workspace-relative file name from the fixture or replay.

    Returns:
        The path under the workspace, preserving its spelling.

    Raises:
        SuiteRunFatal: The target resolves to or outside the workspace root.
    """
    path = work / name
    if path.resolve() == work.resolve() or not path.resolve().is_relative_to(
        work.resolve()
    ):
        raise SuiteRunFatal(f"Path leaves task directory: {name}")
    return path


def stage(case: ScopeCase, work: Path, turn: int) -> dict[str, str]:
    """Release the files and user message for one turn.

    Args:
        case: The fixture containing the conversation and staged files.
        work: The already prepared workspace.
        turn: The one-based turn to release.

    Returns:
        The user message for the newly released turn.

    Raises:
        SuiteRunFatal: The requested turn is outside the case.
    """
    pages = case.get("stage_files", [{} for _ in case["turns"]])
    if not 1 <= turn <= len(pages):
        raise SuiteRunFatal("Turn is outside the case")
    for each_name, each_content in pages[turn - 1].items():
        path = safe_file(work, each_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as destination:
            destination.write(each_content.encode())
    return {"turn": case["turns"][turn - 1]}


def prepare(case: ScopeCase, arm: str, work: Path) -> dict[str, str]:
    """Install the fixture and release its first user turn in a new workspace.

    Args:
        case: The fixture to install and stage.
        arm: The baseline or candidate instruction arm.
        work: The unused workspace path.

    Returns:
        The first user message and the installed instructions digest.
    """
    work.mkdir(parents=True, exist_ok=False)
    files = {**fixture(case), "AGENTS.md": instructions(arm)}
    for each_name, each_contents in files.items():
        path = safe_file(work, each_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(each_contents)
    first = stage(case, work, 1)
    return {**first, "instructions_sha256": digest(files["AGENTS.md"])}


def _decode_file_grade(
    all_missing_or_wrong: list[str], all_unexpected: list[str], case: ScopeCase
) -> FileGrade:
    return {
        "missing_or_wrong": sorted(all_missing_or_wrong),
        "unexpected": sorted(all_unexpected),
        "file_checks_pass": not all_missing_or_wrong and not all_unexpected,
        "artifacts_to_read": case.get("artifacts", {}),
        "final_to_verify": case["report"],
    }


def _encode_file_grade(grade: FileGrade) -> str:
    return json.dumps(grade, indent=JSON_INDENT)


def assess(case: ScopeCase, arm: str, work: Path) -> FileGrade:
    """Compare the workspace with the case's expected changes and exclusions.

    Args:
        case: The grading criteria and complete initial file state.
        arm: The baseline or candidate instruction arm.
        work: The workspace after the final user turn.

    Returns:
        File checks and criteria for the separate text review.
    """
    initial = {**fixture(case), "AGENTS.md": instructions(arm)}
    for each_staged_files in case.get("stage_files", []):
        initial.update(
            {name: content.encode() for name, content in each_staged_files.items()}
        )
    expected = {
        **initial,
        **{key: text.encode() for key, text in case["expect"].items()},
    }
    written = {
        str(entry.relative_to(work).as_posix()): entry
        for entry in work.rglob("*")
        if entry.is_file() or entry.is_symlink()
    }
    artifacts = case.get("artifacts", {})
    all_missing_or_wrong: list[str] = []
    all_unexpected: list[str] = []
    for each_name in set(expected) | set(written) | set(artifacts):
        path = written.get(each_name)
        contents = (
            path.read_bytes()
            if path and path.is_file() and not path.is_symlink()
            else None
        )
        if each_name in artifacts:
            if contents is None or contents == initial.get(each_name):
                all_missing_or_wrong.append(each_name)
        elif each_name not in expected or contents != expected[each_name]:
            (
                all_missing_or_wrong if each_name in case["expect"] else all_unexpected
            ).append(each_name)
    return _decode_file_grade(all_missing_or_wrong, all_unexpected, case)


def main(stream: TextIO) -> None:
    """Run the requested workspace operation and write its receipt.

    Args:
        stream: Destination for the JSON receipt.

    Raises:
        SystemExit: The assessed file checks failed.
    """
    cli = argparse.ArgumentParser(description=__doc__)
    cases = read_cases()
    cli.add_argument("action", choices=ALL_ACTIONS)
    cli.add_argument("case", choices=cases)
    cli.add_argument("arm", choices=ALL_ARMS)
    cli.add_argument("work", type=Path)
    cli.add_argument("--turn", type=int)
    args = cli.parse_args()
    case = cases[args.case]
    if args.action == "stage":
        if args.turn is None or args.turn < NEXT_TURN:
            cli.error("Use --turn 2 or above after the preceding response")
        stream.write(
            json.dumps(stage(case, args.work, args.turn), indent=JSON_INDENT) + "\n"
        )
        return
    if args.action == "prepare":
        stream.write(
            json.dumps(prepare(case, args.arm, args.work), indent=JSON_INDENT) + "\n"
        )
        return
    grade = assess(case, args.arm, args.work)
    stream.write(_encode_file_grade(grade) + "\n")
    if not grade["file_checks_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.stdout)
