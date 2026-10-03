import json
import re
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DECLARATION_FILE = Path(__file__).resolve().parent / "index.d.ts"


def test_public_setting_types_match_plugin_options() -> None:
    manifest = json.loads((PACKAGE_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    declarations = DECLARATION_FILE.read_text(encoding="utf-8")

    assert manifest["types"] == "./types/index.d.ts"
    for type_name, setting in (
        ("Switch", "opus"),
        ("Family", "defaultModel"),
        ("Effort", "effort"),
        ("OffAction", "offAction"),
    ):
        declaration = re.search(rf"^export type {type_name} = (.+)$", declarations, re.MULTILINE)
        assert declaration is not None
        choices = set(re.findall(r"'([^']+)'", declaration.group(1)))
        assert choices == set(manifest["userConfig"][setting]["options"])


def test_plugin_state_declares_every_registered_atom() -> None:
    declarations = DECLARATION_FILE.read_text(encoding="utf-8")
    register_source = (PACKAGE_ROOT / "hooks" / "register.tsx").read_text(encoding="utf-8")
    state = re.search(r"interface PluginState\s*\{\s*'subagent-models':\s*\{([^}]*)\}", declarations)

    assert state is not None
    declared_keys = set(re.findall(r"^\s*(\w+):", state.group(1), re.MULTILINE))
    registered_keys = set(re.findall(r"\batom\(\{ plugin: 'subagent-models', key: '([^']+)'", register_source))
    assert registered_keys
    assert declared_keys == registered_keys
