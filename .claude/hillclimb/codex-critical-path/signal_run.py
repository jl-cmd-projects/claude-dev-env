"""Run one matched handoff from an archived pressure checkpoint."""

import argparse
import contextlib
import io
import shutil
import subprocess
import sys
from pathlib import Path

import draft_run
import pressure_run as console
import signal_rule
from long_run import run_lock
from proof import directory_name, read_json
from trial import HERE, digest, write_json


ARMS = ("unchanged", "signal", "review")
REVIEWER = "reviewer"
ROLE = HERE / "signal_reviewer.txt"
INPUTS = (*console.LOG_NAMES, *console.INPUT_NAMES, "end.json", "reply.txt")
ALERT_HEADING = b"\n\nPending reply check:\n"
ADVICE_HEADING = b"\n\nIndependent check of the pending reply:\n"


def hash_if_present(path):
    return digest(path.read_bytes()) if path.exists() else None


def source_inputs(prefix):
    return {name: hash_if_present(prefix / name) for name in INPUTS}


def alert_for(prefix, source):
    value = signal_rule.evaluate((prefix / "task.txt").read_text(encoding="utf-8"), source["events"], source["reply"])
    if not isinstance(value, str):
        raise ValueError("The signal rule must produce a string.")
    return value.strip().encode()


def verify_issued(directory, overlay, started):
    expected = {"presentation_sha256": overlay["presentation_sha256"],
                "overlay_sha256": digest((directory / "overlay.json").read_bytes()), "started_utc": started["utc"]}
    if read_json(directory / "issued.json") != expected:
        raise ValueError(f"The issued presentation differs from its recorded handoff for {directory.name}.")


def reviewer_evidence(directory, source_name, source_hashes):
    overlay = read_json(directory / "overlay.json")
    prefix = directory / "prefix"
    if (overlay["arm"] != REVIEWER or overlay["source"] != source_name
            or overlay["source_sha256"] != source_hashes or source_inputs(prefix) != source_hashes):
        raise ValueError("The reviewer did not receive the matched source checkpoint.")
    advise = b""
    if (directory / "started.json").exists():
        run = console.replay(directory)
        verify_issued(directory, overlay, run["started"])
        if run["outcome"] and run["outcome"]["outcome"] == "finished":
            advise = (directory / "reply.txt").read_bytes().strip()
    return advise, {
        "id": directory_name(directory.name),
        **{name: hash_if_present(directory / name)
           for name in ("overlay.json", "issued.json", "end.json", "events.jsonl", console.RECEIPTS)},
        "advice_sha256": digest(advise) if advise else None,
    }


def handoff(directory, source_name, arm, review_dir=None):
    prefix = directory / "prefix"
    original = console.replay(prefix)
    inputs = source_inputs(prefix)
    content, instructions = draft_run.presentation(prefix, "baseline")
    alert = alert_for(prefix, original)
    if (arm == "review" and bool(alert)) != (review_dir is not None):
        raise ValueError("An eligible review requires its reviewer directory.")
    advice, review, role = b"", None, None
    if review_dir is not None:
        advice, review = reviewer_evidence(review_dir, source_name, inputs)
    if arm == REVIEWER:
        if not alert:
            raise ValueError("The source checkpoint did not trigger a review.")
        role = ROLE.read_bytes().strip()
        if not role:
            raise ValueError("Reviewer guidance is empty.")
        content += b"\n\n" + role + b"\n"
    if arm != "unchanged" and alert:
        content += ALERT_HEADING + alert + b"\n"
    if advice:
        content += ADVICE_HEADING + advice + b"\n"
    return content, {
        "source": source_name, "arm": arm, "source_sha256": inputs,
        "input_match_key": console.input_match_key(read_json(directory / "run.json")),
        "background_sha256": digest(instructions), "presentation_sha256": digest(content),
        "alert_sha256": digest(alert) if alert else None, "review": review,
        "role_sha256": digest(role) if role else None,
        "rule_sha256": digest(Path(signal_rule.__file__).read_bytes()),
        "runner_sha256": digest(Path(__file__).read_bytes()),
    }


def prepare(directory, source, arm, review_dir=None):
    console.recover(source, directory)
    try:
        content, overlay = handoff(directory, directory_name(source.name), arm, review_dir)
        (directory / "presentation.md").write_bytes(content)
        write_json(directory / "overlay.json", overlay)
    except BaseException:
        shutil.rmtree(directory)
        raise


def start(directory):
    overlay = read_json(directory / "overlay.json")
    data = (directory / "presentation.md").read_bytes()
    if digest(data) != overlay["presentation_sha256"]:
        raise ValueError("The handoff does not match its presentation.")
    with contextlib.redirect_stdout(io.StringIO()):
        console.start(directory, resume=True)
    write_json(directory / "issued.json", {
        "presentation_sha256": digest(data), "overlay_sha256": digest((directory / "overlay.json").read_bytes()),
        "started_utc": read_json(directory / "started.json")["utc"],
    })
    sys.stdout.buffer.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    new = commands.add_parser("prepare")
    new.add_argument("source", type=Path)
    new.add_argument("arm", choices=(*ARMS, REVIEWER))
    new.add_argument("--review-dir", type=Path)
    for name in ("start", "send-draft"):
        commands.add_parser(name)
    commands.add_parser("ps").add_argument("command")
    commands.add_parser("finish").add_argument("reply")
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        if args.action == "prepare":
            prepare(directory, args.source.resolve(), args.arm, args.review_dir.resolve() if args.review_dir else None)
            return 0
        with run_lock(directory):
            if args.action == "start":
                start(directory)
            elif args.action == "ps":
                return console.shell(directory, "powershell", args.command)
            else:
                if args.action == "send-draft" and read_json(directory / "overlay.json")["arm"] == REVIEWER:
                    raise ValueError("A reviewer must finish with advice for this handoff.")
                reply = (directory / "prefix" / "reply.txt").read_text(encoding="utf-8") if args.action == "send-draft" else args.reply
                console.finish(directory, reply)
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
