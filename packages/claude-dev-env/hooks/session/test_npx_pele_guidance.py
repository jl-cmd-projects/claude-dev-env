import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import npx_pele_guidance
from hooks_constants.npx_pele_guidance_constants import (
    NODE_MODULES_DIRECTORY_NAME,
    PACKAGE_MANIFEST_NAME,
    PELE_PACKAGE_NAME,
    PELE_TOOLS_DIRECTORY_NAME,
)

HOOK_SCRIPT = _SESSION_DIR / "npx_pele_guidance.py"
CLAUDE_CONFIG_DIRECTORY_VARIABLE = "CLAUDE_CONFIG_DIR"
JS_FENCE_OPEN = "```js\n"
JS_FENCE_CLOSE = "\n```"
CHAIN_TEXT = "flowchart LR\n  A --> B\n"


def _package_directory_under(claude_root: Path) -> Path:
    return (
        claude_root
        / PELE_TOOLS_DIRECTORY_NAME
        / PELE_PACKAGE_NAME
        / NODE_MODULES_DIRECTORY_NAME
        / PELE_PACKAGE_NAME
    )


def _write_installed_pele(claude_root: Path, version: str) -> Path:
    package_directory = _package_directory_under(claude_root)
    (package_directory / "dist").mkdir(parents=True)
    (package_directory / PACKAGE_MANIFEST_NAME).write_text(
        json.dumps({"name": PELE_PACKAGE_NAME, "version": version, "type": "module"}),
        encoding="utf-8",
    )
    (package_directory / "dist" / "pele.js").write_text(
        "export function render(text) {\n    return { svg: `<svg>${text.length}</svg>` };\n}\n",
        encoding="utf-8",
    )
    return package_directory


def _payload(command_text: str) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command_text},
    }


def _run_hook(payload_text: str, claude_root: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment[CLAUDE_CONFIG_DIRECTORY_VARIABLE] = str(claude_root)
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=payload_text,
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )


@pytest.mark.parametrize(
    "command_text",
    [
        "npx pele",
        "npx -y pele chain.mmd",
        "npx --yes pele@1.12.0 chain.mmd",
        "cd diagrams && npx pele chain.mmd",
        "npm exec pele chain.mmd",
        "npx.cmd pele chain.mmd",
    ],
)
def test_npx_pele_commands_match(command_text: str) -> None:
    assert npx_pele_guidance.is_npx_pele_command({"command": command_text})


@pytest.mark.parametrize(
    "command_text",
    [
        "npx prettier --check .",
        "npm install pele",
        "npx -y claude-dev-env@latest",
        "npx pelee",
        "npx -y create-pele-app my-app",
        "echo pele",
    ],
)
def test_other_commands_do_not_match(command_text: str) -> None:
    assert not npx_pele_guidance.is_npx_pele_command({"command": command_text})


@pytest.mark.parametrize("tool_input", [None, "npx pele", {}, {"command": 7}])
def test_input_without_a_command_string_does_not_match(tool_input: object) -> None:
    assert not npx_pele_guidance.is_npx_pele_command(tool_input)


def test_installed_version_reads_the_manifest(tmp_path: Path) -> None:
    package_directory = _write_installed_pele(tmp_path, "1.12.0")
    assert npx_pele_guidance.installed_pele_version(package_directory) == "1.12.0"


def test_installed_version_is_none_without_a_manifest(tmp_path: Path) -> None:
    assert npx_pele_guidance.installed_pele_version(_package_directory_under(tmp_path)) is None


@pytest.mark.parametrize("manifest_text", ["not json", '["list"]', '{"version": 1}'])
def test_unreadable_manifest_reads_as_no_version(tmp_path: Path, manifest_text: str) -> None:
    package_directory = _package_directory_under(tmp_path)
    package_directory.mkdir(parents=True)
    (package_directory / PACKAGE_MANIFEST_NAME).write_text(manifest_text, encoding="utf-8")
    assert npx_pele_guidance.installed_pele_version(package_directory) is None


def test_package_directory_follows_the_claude_config_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CLAUDE_CONFIG_DIRECTORY_VARIABLE, str(tmp_path))
    assert npx_pele_guidance.pele_package_directory() == _package_directory_under(tmp_path)


def test_installed_copy_gets_its_version_path_and_snippet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CLAUDE_CONFIG_DIRECTORY_VARIABLE, str(tmp_path))
    package_directory = _write_installed_pele(tmp_path, "1.12.0")
    hook_output = npx_pele_guidance.decide_hook_output(_payload("npx pele chain.mmd"))
    assert hook_output is not None
    specific_output = hook_output["hookSpecificOutput"]
    assert specific_output["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in specific_output
    context_text = specific_output["additionalContext"]
    assert "could not determine executable to run" in context_text
    assert f"Pele 1.12.0 is installed at {package_directory}" in context_text
    assert json.dumps(str(package_directory / "dist" / "pele.js")) in context_text
    assert "pele.run" not in context_text


def test_missing_copy_points_to_the_playground(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CLAUDE_CONFIG_DIRECTORY_VARIABLE, str(tmp_path))
    hook_output = npx_pele_guidance.decide_hook_output(_payload("npx -y pele chain.mmd"))
    assert hook_output is not None
    context_text = hook_output["hookSpecificOutput"]["additionalContext"]
    assert "could not determine executable to run" in context_text
    assert "is not installed at" in context_text
    assert "playground at pele.run" in context_text
    assert "pathToFileURL" not in context_text


def test_installed_snippet_renders_an_svg_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    claude_root = tmp_path / "claude"
    _write_installed_pele(claude_root, "1.12.0")
    monkeypatch.setenv(CLAUDE_CONFIG_DIRECTORY_VARIABLE, str(claude_root))
    work_directory = tmp_path / "work"
    work_directory.mkdir()
    (work_directory / "chain.mmd").write_text(CHAIN_TEXT, encoding="utf-8")
    context_text = npx_pele_guidance.guidance_text()
    snippet = context_text.split(JS_FENCE_OPEN, 1)[1].split(JS_FENCE_CLOSE, 1)[0]
    (work_directory / "render.mjs").write_text(snippet, encoding="utf-8")
    completed = subprocess.run(
        ["node", "render.mjs"],
        cwd=work_directory,
        capture_output=True,
        text=True,
        check=True,
    )
    rendered_svg = (work_directory / "chain.svg").read_text(encoding="utf-8")
    assert rendered_svg == f"<svg>{len(CHAIN_TEXT)}</svg>"
    assert "svg bytes:" in completed.stdout


def test_decide_hook_output_is_silent_for_other_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CLAUDE_CONFIG_DIRECTORY_VARIABLE, str(tmp_path))
    assert npx_pele_guidance.decide_hook_output(_payload("npm install pele")) is None


def test_hook_prints_the_guidance_as_json_for_npx_pele(tmp_path: Path) -> None:
    completed = _run_hook(json.dumps(_payload("npx pele chain.mmd")), tmp_path)
    hook_output = json.loads(completed.stdout)
    assert hook_output["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in hook_output["hookSpecificOutput"]
    assert "playground at pele.run" in hook_output["hookSpecificOutput"]["additionalContext"]


def test_hook_is_silent_on_malformed_stdin(tmp_path: Path) -> None:
    completed = _run_hook("not json", tmp_path)
    assert completed.returncode == 0
    assert completed.stdout == ""
