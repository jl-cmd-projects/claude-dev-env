import json
import re
from pathlib import Path


HOOKS_DIRECTORY = Path(__file__).resolve().parent
REGISTER_FILE = HOOKS_DIRECTORY / "register.tsx"


def test_hook_manifest_loads_register_module() -> None:
    modules = json.loads((HOOKS_DIRECTORY / "hooks.json").read_text(encoding="utf-8"))["modules"]

    assert modules == ["./register.tsx"]
    assert REGISTER_FILE.is_file()


def test_register_exposes_subagent_handlers() -> None:
    source = REGISTER_FILE.read_text(encoding="utf-8")
    events = set(re.findall(r"\bon\('([^']+)',\s*async(?: function\*)?\s*\(", source))

    assert "export const register: Register = (on, options: PluginOptions) => {" in source
    assert {"session.start", "agent.offer", "agent.spawn", "skill.prompt", "turn.step"} <= events
