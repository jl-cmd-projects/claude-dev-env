"""Install a pinned checkout into a new disposable home and verify Codex's input."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from completion_eval.config import study
from completion_eval.errors import EvidenceRunFatal


def digest(content_bytes: bytes) -> str:
    return hashlib.sha256(content_bytes).hexdigest()


def verify_input(environment: dict, prompt: Path, directory: Path, all_overrides: tuple[str, ...]) -> str:
    """Verify that Codex receives the installed instruction as developer input.

    Args:
        environment: Disposable installation environment.
        prompt: Installed model instruction file.
        directory: Working directory used for rendering.
        all_overrides: Selected model and execution flags.

    Returns:
        Hash of normalized render metadata.

    Raises:
        EvidenceRunFatal: The rendered input omits the installed instruction.
    """
    rendered = subprocess.run(
        ["codex", *all_overrides, "debug", "prompt-input", "Check the receipt."],
        cwd=directory, env=environment, capture_output=True, text=True,
        check=True, timeout=study.PROMPT_CHECK_SECONDS,
    )
    messages = json.loads(rendered.stdout)
    expected = prompt.read_text(encoding="utf-8").strip()
    has_prompt = False
    normalized = []
    for each_message in messages:
        for each_content in each_message.get("content", []):
            if each_message.get("role") == "developer" and each_content.get("text", "").strip() == expected:
                has_prompt = True
                each_content["text"] = "<tested prompt>"
        normalized.append({field: each_message[field] for field in ("type", "role", "content", "tools") if field in each_message})
    if not has_prompt:
        raise EvidenceRunFatal("The installed model prompt is absent from Codex developer input")
    serialized = json.dumps(normalized, sort_keys=True).replace(str(directory), "<fixture>")
    return digest(serialized.encode())


def install(source: Path, destination: Path, model: str) -> dict:
    """Install from a pinned package and check its rendered prompt.

    Args:
        source: Clean source checkout.
        destination: New disposable installation home.
        model: Model selection for the render check.

    Returns:
        Source revision and installed prompt digest.

    Raises:
        EvidenceRunFatal: Source, installation, and renderer disagree.
    """
    package = source / "packages/claude-dev-env"
    head = subprocess.check_output(study.ALL_GIT_HEAD_ARGS, cwd=source, text=True).strip()
    dirty = subprocess.check_output(
        study.ALL_GIT_STATUS_ARGS, cwd=source, text=True,
    )
    if dirty:
        raise EvidenceRunFatal("Install from a clean pinned package checkout")
    destination.mkdir(parents=True, exist_ok=False)
    codex_home = destination / study.CODEX_DIRECTORY
    env = dict(os.environ)
    for each_key in study.ALL_INHERITED_OPTIONS:
        env.pop(each_key, None)
    env.update(
        HOME=str(destination), USERPROFILE=str(destination), CODEX_HOME=str(codex_home),
        GIT_CONFIG_GLOBAL=str(destination / study.GIT_CONFIGURATION), TMP=str(destination), TEMP=str(destination),
    )
    for each_name in study.ALL_OPTIONAL_INSTALLS:
        env["CDE_INSTALL_" + each_name] = "0"
    with (destination / "install.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            ["node", "bin/install.mjs"], cwd=package, env=env, check=True,
            stdout=log, stderr=subprocess.STDOUT, timeout=study.APPROVED_SECONDS,
        )
    config = tomllib.loads((codex_home / "config.toml").read_text(encoding="utf-8"))
    prompt = Path(config["model_instructions_file"]).resolve()
    shipped = package / "system-prompts/codex-sol.md"
    if prompt != codex_home / "codex-sol.md" or prompt.read_bytes() != shipped.read_bytes():
        raise EvidenceRunFatal("Installed model prompt differs from pinned source")
    with tempfile.TemporaryDirectory() as scratch:
        verify_input(env, prompt, Path(scratch), (
            "--model", model, "-c", 'model_reasoning_effort="high"',
            "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
        ))
    metadata = {"revision": head, "prompt_sha256": digest(shipped.read_bytes())}
    (destination / "install.json").write_text(json.dumps(metadata, indent=study.JSON_INDENT), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("new_home", type=Path)
    parser.add_argument("--model", default="gpt-6.1-sol")
    args = parser.parse_args()
    json.dump(install(args.source.resolve(), args.new_home.resolve(), args.model), sys.stdout)
