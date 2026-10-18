"""Load host settings for the efficient-review runner."""

from __future__ import annotations

import json
import os
from pathlib import Path

from tools.config import efficient_review_constants as c

ALL_SETTING_DEFAULTS: dict[str, object] = {
    "owner_display_name": "the owner",
    "excluded_accounts": [],
    "known_accounts": [],
    "broker_relative_parts": [".claude", "scripts", "account_broker.py"],
    "launcher_directory_parts": [".local", "bin"],
    "launcher_prefix": "claude-",
    "launcher_suffix": ".cmd",
    "launcher_home_pattern": 'set "CLAUDE_CONFIG_DIR=(.+)"',
    "codex_catalog_module": "",
    "rules_root": "",
    "rules_paths": ["docs/review/review.md"],
    "dispatch_repository": "",
    "dispatch_workflow_file": "efficient-review.yml",
    "dispatch_workflow_id": "",
    "dispatch_ref": "main",
    "results_branch_prefix": "efficient-review-results",
    "read_token_environment": "",
    "hook_owner": "",
    "hook_repository": "",
    "hook_dispatch_tool": "mcp__github__actions_run_trigger",
    "hook_shell_tools": ["Bash", "PowerShell"],
}


def load_settings() -> dict[str, object]:
    """Return settings.json, then the environment override, over the neutral defaults.

    Returns:
        The merged settings mapping.
    """
    all_settings = dict(ALL_SETTING_DEFAULTS)
    all_settings.update(_read_object(c.SETTINGS_PATH))
    override = os.environ.get(c.SETTINGS_ENVIRONMENT)
    if override:
        all_settings.update(_read_object(Path(override)))
    return all_settings


def string_list(all_settings: dict[str, object], key: str) -> tuple[str, ...]:
    """Return one settings value as a tuple of strings.

    Args:
        all_settings: The merged settings.
        key: The settings key.

    Returns:
        The string items stored under that key.
    """
    stored_setting = all_settings.get(key, ())
    if not isinstance(stored_setting, list):
        return ()
    return tuple(str(each_entry) for each_entry in stored_setting)


def _read_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding=c.JSON_READ_ENCODING))
    if not isinstance(loaded, dict):
        return {}
    return loaded
