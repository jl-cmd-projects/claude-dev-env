"""Stage pinned instructions and a work order for one fresh Codex worker."""

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

SOURCE_REVISION = "6086051cb6fcd21dc227e91711c8d54fd2a31eac"
SOURCE_PATH = "packages/claude-dev-env/system-prompts/codex-sol.md"
ANCHOR = "Do not use tools to send messages to others"


def instructions(arm: str) -> bytes:
    """Return the full instruction file for one comparison arm."""
    directory = Path(__file__).resolve().parent
    baseline = subprocess.check_output(["git", "show", f"{SOURCE_REVISION}:{SOURCE_PATH}"], cwd=directory).decode()
    if arm == "baseline":
        return baseline.encode()
    if arm != "candidate" or baseline.count(ANCHOR) != 1:
        raise ValueError("Unknown prompt arm or missing insertion point")
    candidate = (directory / "candidate.md").read_text().strip()
    return baseline.replace(ANCHOR, f"{candidate}\n\n{ANCHOR}", 1).encode()


def stage(arm: str, case: str, endpoint: str, folder: Path) -> dict[str, str]:
    """Write the pinned instructions and service-generated order in a fresh directory."""
    fixture = Path(__file__).with_name("fixture.py")
    order = subprocess.check_output([sys.executable, str(fixture), "prompt", "--case", case, "--base-url", endpoint])
    folder.mkdir(parents=True, exist_ok=False)
    artifacts = {"AGENTS.md": instructions(arm), "order.md": order}
    for name, body in artifacts.items():
        (folder / name).write_bytes(body)
    return {name: hashlib.sha256(body).hexdigest() for name, body in artifacts.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=["baseline", "candidate"])
    parser.add_argument("case")
    parser.add_argument("endpoint")
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    print(stage(args.arm, args.case, args.endpoint, args.folder))
