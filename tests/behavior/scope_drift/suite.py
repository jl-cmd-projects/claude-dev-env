"""Prepare a fresh working directory and compare its files to the case oracle."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASELINE = "3ab5949a8ea9c1ad11280e8e9a524bee2587bb8a"
PROMPT = "packages/claude-dev-env/system-prompts/codex-sol.md"
ANCHOR = "Infer the user's intent and task scope from the instructions and prior conversation context. Your job is to bias towards action and carry the user's intended task to completion."


def digest(contents):
    return hashlib.sha256(contents).hexdigest()


def read_cases():
    cases = {}
    for name in ("cases.json", "holdouts.json", "supervision.json", "relay.json"):
        for case in json.loads((ROOT / name).read_text(encoding="utf-8")):
            if case["id"] in cases:
                raise ValueError(f"Duplicate case: {case['id']}")
            cases[case["id"]] = case
    return cases


def fixture(case):
    files = (
        json.loads((ROOT / case["base"]).read_text(encoding="utf-8"))
        if "base" in case
        else {}
    )
    files.update(case["files"])
    return {
        path: contents.encode()
        for path, contents in files.items()
        if contents is not None
    }


def instructions(arm):
    base = subprocess.check_output(["git", "show", f"{BASELINE}:{PROMPT}"], cwd=ROOT)
    if arm == "baseline":
        return base
    if base.count(ANCHOR.encode()) != 1:
        raise ValueError("Pinned insertion point must occur once")
    return base.replace(
        ANCHOR.encode(),
        ANCHOR.encode() + b"\n\n" + (ROOT / "candidate.txt").read_bytes().strip(),
    )


def safe_file(work, name):
    path = work / name
    if path.resolve() == work.resolve() or not path.resolve().is_relative_to(
        work.resolve()
    ):
        raise ValueError(f"Path leaves task directory: {name}")
    return path


def stage(case, work, turn):
    pages = case.get("stage_files", [{} for _ in case["turns"]])
    if not 1 <= turn <= len(pages):
        raise ValueError("Turn is outside the case")
    for name, content in pages[turn - 1].items():
        path = safe_file(work, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as destination:
            destination.write(content.encode())
    return {"turn": case["turns"][turn - 1]}


def prepare(case, arm, work):
    work.mkdir(parents=True, exist_ok=False)
    files = {**fixture(case), "AGENTS.md": instructions(arm)}
    for name, contents in files.items():
        path = safe_file(work, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    first = stage(case, work, 1)
    return {**first, "instructions_sha256": digest(files["AGENTS.md"])}


def assess(case, arm, work):
    initial = {**fixture(case), "AGENTS.md": instructions(arm)}
    for files in case.get("stage_files", []):
        initial.update({name: content.encode() for name, content in files.items()})
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
    missing_or_wrong = []
    unexpected = []
    for name in set(expected) | set(written) | set(artifacts):
        path = written.get(name)
        contents = (
            path.read_bytes()
            if path and path.is_file() and not path.is_symlink()
            else None
        )
        if name in artifacts:
            if contents is None or contents == initial.get(name):
                missing_or_wrong.append(name)
        elif name not in expected or contents != expected[name]:
            (missing_or_wrong if name in case["expect"] else unexpected).append(name)
    return {
        "missing_or_wrong": sorted(missing_or_wrong),
        "unexpected": sorted(unexpected),
        "file_checks_pass": not missing_or_wrong and not unexpected,
        "artifacts_to_read": artifacts,
        "final_to_verify": case["report"],
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=["prepare", "stage", "assess"])
    cli.add_argument("case", choices=read_cases())
    cli.add_argument("arm", choices=["baseline", "candidate"])
    cli.add_argument("work", type=Path)
    cli.add_argument("--turn", type=int)
    args = cli.parse_args()
    if args.action == "stage":
        if args.turn is None or args.turn < 2:
            cli.error("Use --turn 2 or above after the preceding response")
        print(
            json.dumps(stage(read_cases()[args.case], args.work, args.turn), indent=2)
        )
        return
    function = prepare if args.action == "prepare" else assess
    assessment = function(read_cases()[args.case], args.arm, args.work)
    print(json.dumps(assessment, indent=2))
    if args.action == "assess" and not assessment["file_checks_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
