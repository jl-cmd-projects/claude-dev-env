"""Keep the hook feature map aligned with live registrations."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

HOOKS_DIRECTORY = Path(__file__).resolve().parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from hooks_constants.bash_post_call_dispatcher_constants import (
    ALL_BASH_POST_TOOL_USE_HOSTED_HOOK_ENTRIES,
)
from hooks_constants.bash_pre_tool_use_dispatcher_constants import ALL_BASH_HOSTED_HOOK_ENTRIES
from hooks_constants.post_tool_use_dispatcher_constants import ALL_POST_HOSTED_HOOK_ENTRIES
from hooks_constants.pre_tool_use_dispatcher_constants import ALL_HOSTED_HOOK_ENTRIES


FEATURES_DIRECTORY = HOOKS_DIRECTORY / "features"
SCRIPT_PATTERN = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/hooks/([^\s\"]+)")
CHECK_PATTERN = re.compile(r"^- `([^`]+)`", re.MULTILINE)
FAMILY_LINK_PATTERN = re.compile(r"\]\(\./([a-z0-9-]+\.md)\)")
SECTION_PATTERN = re.compile(r"^## (.+)$", re.MULTILINE)
EXPECTED_SECTIONS = ["Checks", "When it fires", "Proving it", "Gotchas"]


def registered_hook_commands() -> list[str]:
    """Return every command string registered in hooks.json."""
    registrations = json.loads((HOOKS_DIRECTORY / "hooks.json").read_text(encoding="utf-8"))
    return [
        hook["command"]
        for all_groups in registrations["hooks"].values()
        for group in all_groups
        for hook in group["hooks"]
    ]


def registered_script_paths() -> set[str]:
    """Return paths named by the hook registration and hosted rosters."""
    script_paths = {"blocking/state_description_blocker.py"}
    for command in registered_hook_commands():
        matching_paths = SCRIPT_PATTERN.findall(command)
        assert matching_paths, f"Hook command has no hooks/ script: {command}"
        script_paths.update(matching_paths)

    for roster in (
        ALL_HOSTED_HOOK_ENTRIES,
        ALL_BASH_HOSTED_HOOK_ENTRIES,
        ALL_BASH_POST_TOOL_USE_HOSTED_HOOK_ENTRIES,
        ALL_POST_HOSTED_HOOK_ENTRIES,
    ):
        script_paths.update(entry.script_relative_path for entry in roster)
    return script_paths


def family_paths() -> list[Path]:
    """Return the Markdown pages that hold script checks."""
    return sorted(path for path in FEATURES_DIRECTORY.glob("*.md") if path.name != "README.md")


def check_paths(family_path: Path) -> list[str]:
    """Read script paths from one family's Checks section."""
    page = family_path.read_text(encoding="utf-8")
    checks = page.split("## Checks\n", 1)
    assert len(checks) == 2, f"Missing Checks section in {family_path.name}"
    checks_section = checks[1].split("\n## ", 1)[0]
    return CHECK_PATTERN.findall(checks_section)


def test_every_registered_hook_appears_once() -> None:
    mapped_paths = Counter(path for family_path in family_paths() for path in check_paths(family_path))
    registered_paths = registered_script_paths()
    for script_path in sorted(registered_paths):
        assert mapped_paths[script_path] == 1, (
            f"Registered script {script_path} appears {mapped_paths[script_path]} times in Checks"
        )
    for script_path in sorted(mapped_paths):
        assert script_path in registered_paths, f"Unregistered script {script_path} appears in Checks"


def test_every_check_names_an_existing_hook() -> None:
    hooks_root = HOOKS_DIRECTORY.resolve()
    for family_path in family_paths():
        for script_path in check_paths(family_path):
            candidate = (hooks_root / script_path).resolve()
            assert candidate.is_relative_to(hooks_root), f"Script escapes hooks/: {script_path}"
            assert candidate.is_file(), f"Script does not exist under hooks/: {script_path}"


def test_readme_lists_every_family_once() -> None:
    readme = (FEATURES_DIRECTORY / "README.md").read_text(encoding="utf-8")
    families = readme.split("## Families\n", 1)
    assert len(families) == 2, "README.md is missing the Families section"
    listed_names = FAMILY_LINK_PATTERN.findall(families[1])
    listed_counts = Counter(listed_names)
    existing_names = {path.name for path in family_paths()}
    for family_name in sorted(existing_names | set(listed_names)):
        assert listed_counts[family_name] == 1, (
            f"Family {family_name} appears {listed_counts[family_name]} times in README.md"
        )
        assert family_name in existing_names, f"README.md names missing family {family_name}"


def test_every_family_has_four_sections_in_order() -> None:
    for family_path in family_paths():
        headings = SECTION_PATTERN.findall(family_path.read_text(encoding="utf-8"))
        assert headings == EXPECTED_SECTIONS, f"{family_path.name} has sections {headings}"
