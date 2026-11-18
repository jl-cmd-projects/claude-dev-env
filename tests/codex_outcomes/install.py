"""Install a pinned checkout into a new disposable home and verify Codex's input."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import tomllib
from pathlib import Path


def digest(content_bytes: bytes) -> str:
    return hashlib.sha256(content_bytes).hexdigest()


def verify_input(environment: dict, prompt: Path, directory: Path, overrides=()) -> str:
    rendered = subprocess.run(
        ["codex", *overrides, "debug", "prompt-input", "Check the receipt."],
        cwd=directory, env=environment, capture_output=True, text=True,
        check=True, timeout=45,
    )
    messages = json.loads(rendered.stdout)
    expected = prompt.read_text(encoding="utf-8").strip()
    found = False
    normalized = []
    for message in messages:
        for content in message.get("content", []):
            if message.get("role") == "developer" and content.get("text", "").strip() == expected:
                found = True
                content["text"] = "<tested prompt>"
        normalized.append({field: message[field] for field in ("type", "role", "content", "tools") if field in message})
    if not found:
        raise ValueError("The installed model prompt is absent from Codex developer input")
    serialized = json.dumps(normalized, sort_keys=True).replace(str(directory), "<fixture>")
    return digest(serialized.encode())


def install(source: Path, destination: Path, model: str) -> dict:
    package = source / "packages/claude-dev-env"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "packages/claude-dev-env"], cwd=source, text=True,
    )
    if dirty:
        raise ValueError("Install from a clean pinned package checkout")
    destination.mkdir(parents=True, exist_ok=False)
    codex_home = destination / ".codex"
    env = dict(os.environ)
    for key in ("CLAUDE_CONFIG_DIR", "LLM_SETTINGS_PROFILES_ROOT", "CLAUDE_DEV_ENV_INSTALL_FAULT"):
        env.pop(key, None)
    env.update(
        HOME=str(destination), USERPROFILE=str(destination), CODEX_HOME=str(codex_home),
        GIT_CONFIG_GLOBAL=str(destination / ".gitconfig"), TMP=str(destination), TEMP=str(destination),
    )
    for name in ("PSTACK", "DEEPSTACK", "PELE", "USAGE_WRAPUP", "SUBAGENT_MODELS", "SECURITY_GUIDANCE"):
        env["CDE_INSTALL_" + name] = "0"
    with (destination / "install.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            ["node", "bin/install.mjs"], cwd=package, env=env, check=True,
            stdout=log, stderr=subprocess.STDOUT, timeout=180,
        )
    config = tomllib.loads((codex_home / "config.toml").read_text(encoding="utf-8"))
    prompt = Path(config["model_instructions_file"]).resolve()
    shipped = package / "system-prompts/codex-sol.md"
    if prompt != codex_home / "codex-sol.md" or prompt.read_bytes() != shipped.read_bytes():
        raise ValueError("Installed model prompt differs from pinned source")
    with tempfile.TemporaryDirectory() as scratch:
        verify_input(env, prompt, Path(scratch), (
            "--model", model, "-c", 'model_reasoning_effort="high"',
            "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
        ))
    metadata = {"revision": head, "prompt_sha256": digest(shipped.read_bytes())}
    (destination / "install.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("new_home", type=Path)
    parser.add_argument("--model", default="gpt-6.1-sol")
    args = parser.parse_args()
    print(json.dumps(install(args.source.resolve(), args.new_home.resolve(), args.model)))
