"""Prepare a participant's instructions and work order in a fresh directory."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def stage(arm: str, case: str, endpoint: str, folder: Path, service: Path) -> dict[str, str]:
    """Write the instructions and order used in one fresh session.

    Args:
        arm: Instruction variant selected by the operator.
        case: Fixture work order.
        endpoint: Loopback address for this pair.
        folder: Fresh participant directory.
        service: Fixture entry point responsible for rendering the order.

    Returns:
        SHA-256 digests of both files.

    Raises:
        ValueError: The pinned prompt has a different permission paragraph.
    """
    directory = Path(__file__).resolve().parent
    revision = json.loads((directory / "evidence" / "launch.json").read_text())["source_commit"]
    source = "packages/claude-dev-env/system-prompts/codex-sol.md"
    base = subprocess.check_output(["git", "show", f"{revision}:{source}"], cwd=directory)
    instructions = base.decode("utf-8")
    if arm != "baseline":
        anchor = "Do not use tools to send messages to others"
        if instructions.count(anchor) != 1:
            raise ValueError("The permission paragraph has changed")
        paragraph = (directory / f"{arm}.md").read_text().strip()
        instructions = instructions.replace(anchor, f"{paragraph}\n\n{anchor}", 1)
    order = subprocess.check_output(
        [sys.executable, str(service), "prompt", "--case", case, "--base-url", endpoint]
    )
    folder.mkdir(parents=True, exist_ok=False)
    artifacts = {"AGENTS.md": instructions.encode(), "order.md": order}
    for each_name, each_content in artifacts.items():
        (folder / each_name).write_bytes(each_content)
    return {name: hashlib.sha256(content).hexdigest() for name, content in artifacts.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=["baseline", "candidate", "revised"])
    parser.add_argument("case")
    parser.add_argument("endpoint")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--service", type=Path, default=Path(__file__).with_name("service.py"))
    settings = parser.parse_args()
    digests = stage(settings.arm, settings.case, settings.endpoint, settings.folder, settings.service)
    json.dump(digests, sys.stdout)
