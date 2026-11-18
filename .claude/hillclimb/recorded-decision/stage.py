"""Stage pinned instructions and a work order for one fresh Codex worker."""

import argparse
import hashlib
import subprocess
import sys
import json
from pathlib import Path

from config.stage_constants import ANCHOR, SOURCE_PATH, SOURCE_REVISION


def instructions(arm: str) -> bytes:
    """Return the full instruction file for the requested comparison arm.

    Args:
        arm: Selected instruction variant.

    Returns:
        UTF-8 encoded project instructions.

    Raises:
        ValueError: The prompt variant or insertion point is unknown.
    """
    directory = Path(__file__).resolve().parent
    baseline = subprocess.check_output(["git", "show", f"{SOURCE_REVISION}:{SOURCE_PATH}"], cwd=directory).decode()
    if arm == "baseline":
        return baseline.encode()
    if arm != "candidate" or baseline.count(ANCHOR) != 1:
        raise ValueError("Unknown prompt arm or missing insertion point")
    candidate = (directory / "candidate.md").read_text().split("```text\n", 1)[1].split("\n```", 1)[0]
    return baseline.replace(ANCHOR, f"{candidate}\n\n{ANCHOR}", 1).encode()


def stage(arm: str, case: str, endpoint: str, folder: Path) -> dict[str, str]:
    """Write instructions and a service-generated order in a fresh directory.

    Args:
        arm: Selected instruction variant.
        case: Fixture assignment.
        endpoint: Service URL for the pair.
        folder: Fresh participant directory.

    Returns:
        Digests of the staged files.
    """
    fixture = Path(__file__).with_name("fixture.py")
    order = subprocess.check_output([sys.executable, str(fixture), "prompt", "--case", case, "--base-url", endpoint])
    folder.mkdir(parents=True, exist_ok=False)
    artifacts = {"AGENTS.md": instructions(arm), "order.md": order}
    for each_name, each_body in artifacts.items():
        (folder / each_name).write_bytes(each_body)
    return {name: hashlib.sha256(body).hexdigest() for name, body in artifacts.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=["baseline", "candidate"])
    parser.add_argument("case")
    parser.add_argument("endpoint")
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    json.dump(stage(args.arm, args.case, args.endpoint, args.folder), sys.stdout)
