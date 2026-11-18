"""Prepare a participant's instructions and work order in a fresh directory."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
REVISION = "3ab5949a8ea9c1ad11280e8e9a524bee2587bb8a"
SOURCE = "packages/claude-dev-env/system-prompts/codex-sol.md"
ANCHOR = "Do not use tools to send messages to others"


def stage(arm, case, endpoint, folder, service):
    base = subprocess.check_output(["git", "show", f"{REVISION}:{SOURCE}"], cwd=HERE)
    instructions = base.decode("utf-8")
    if arm != "baseline":
        if instructions.count(ANCHOR) != 1:
            raise ValueError("The permission paragraph has changed")
        paragraph = (HERE / f"{arm}.md").read_text().strip()
        instructions = instructions.replace(ANCHOR, f"{paragraph}\n\n{ANCHOR}", 1)
    order = subprocess.check_output(
        [sys.executable, str(service), "prompt", "--case", case, "--base-url", endpoint]
    )
    folder.mkdir(parents=True, exist_ok=False)
    artifacts = {"AGENTS.md": instructions.encode(), "order.md": order}
    for name, content in artifacts.items():
        (folder / name).write_bytes(content)
    return {name: hashlib.sha256(content).hexdigest() for name, content in artifacts.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=["baseline", "candidate", "revised"])
    parser.add_argument("case")
    parser.add_argument("endpoint")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--service", type=Path, default=HERE / "service.py")
    args = parser.parse_args()
    print(json.dumps(stage(args.arm, args.case, args.endpoint, args.folder, args.service)))
