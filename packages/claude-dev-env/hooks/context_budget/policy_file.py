"""Parse ``.claude/context-budget.json`` and locate it from an edited file.

Unknown keys are ignored, so a policy file another tool extends still parses.
"""

from __future__ import annotations

import json
from pathlib import Path

from context_budget.model import (
    BaselineEntry,
    BudgetPolicy,
    ContextBudgetPolicyError,
    ContextKind,
    HookBudget,
)
from hooks_constants.context_budget_constants import (
    ALL_DEFAULT_KIND_SPECS,
    ALL_POLICY_PATH_PARTS,
    BASELINE_FILES_KEY,
    BASELINE_HOOKS_KEY,
    BASELINE_KEY,
    CHAR_LIMIT_KEY,
    COMMAND_KEY,
    DEFAULT_SECTION_DETAIL_LINE_LIMIT,
    GIT_MARKER_NAME,
    HOOKS_KEY,
    KINDS_KEY,
    LINE_LIMIT_KEY,
    LINES_KEY,
    NAME_KEY,
    PATTERNS_KEY,
    POLICY_ERROR_BAD_FIELD,
    POLICY_ERROR_NOT_OBJECT,
    SECTION_DETAIL_LINE_LIMIT_KEY,
    SECTION_RULE_KEY,
    SECTIONS_KEY,
    STDIN_KEY,
    UTF8_ENCODING,
)


def default_policy() -> BudgetPolicy:
    """Return the built-in policy for a repository with no policy file.

    Returns:
        The default kinds with an empty baseline.
    """
    return BudgetPolicy(
        section_detail_line_limit=DEFAULT_SECTION_DETAIL_LINE_LIMIT,
        all_kinds=tuple(
            ContextKind(each_name, each_patterns, each_limit, each_rule)
            for each_name, each_patterns, each_limit, each_rule in ALL_DEFAULT_KIND_SPECS
        ),
    )


def _bad_field(field_name: str) -> ContextBudgetPolicyError:
    return ContextBudgetPolicyError(POLICY_ERROR_BAD_FIELD.format(field=field_name))


def _integer(raw_value: object, field_name: str) -> int:
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise _bad_field(field_name)
    return raw_value


def _text(raw_value: object, field_name: str) -> str:
    if not isinstance(raw_value, str):
        raise _bad_field(field_name)
    return raw_value


def _mapping(raw_value: object, field_name: str) -> dict:
    if not isinstance(raw_value, dict):
        raise _bad_field(field_name)
    return raw_value


def _texts(raw_value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        raise _bad_field(field_name)
    return tuple(_text(each_item, field_name) for each_item in raw_value)


def _items(raw_value: object, field_name: str) -> list:
    if not isinstance(raw_value, list):
        raise _bad_field(field_name)
    return raw_value


def _parse_kind(raw_kind: object) -> ContextKind:
    kind_by_key = _mapping(raw_kind, KINDS_KEY)
    raw_limit = kind_by_key.get(LINE_LIMIT_KEY)
    return ContextKind(
        _text(kind_by_key.get(NAME_KEY), NAME_KEY),
        _texts(kind_by_key.get(PATTERNS_KEY), PATTERNS_KEY),
        None if raw_limit is None else _integer(raw_limit, LINE_LIMIT_KEY),
        kind_by_key.get(SECTION_RULE_KEY) is True,
    )


def _parse_hook(raw_hook: object) -> HookBudget:
    hook_by_key = _mapping(raw_hook, HOOKS_KEY)
    return HookBudget(
        _text(hook_by_key.get(NAME_KEY), NAME_KEY),
        _texts(hook_by_key.get(COMMAND_KEY), COMMAND_KEY),
        json.dumps(hook_by_key.get(STDIN_KEY, {})),
        _integer(hook_by_key.get(CHAR_LIMIT_KEY), CHAR_LIMIT_KEY),
    )


def _parse_baseline_entry(raw_entry: object) -> BaselineEntry:
    entry_by_key = _mapping(raw_entry, BASELINE_FILES_KEY)
    return BaselineEntry(
        _integer(entry_by_key.get(LINES_KEY), LINES_KEY),
        _texts(entry_by_key.get(SECTIONS_KEY, []), SECTIONS_KEY),
    )


def _parse_baseline(raw_baseline: object) -> tuple[dict[str, BaselineEntry], dict[str, int]]:
    baseline_by_key = _mapping(raw_baseline, BASELINE_KEY)
    raw_files = _mapping(baseline_by_key.get(BASELINE_FILES_KEY, {}), BASELINE_FILES_KEY)
    raw_hooks = _mapping(baseline_by_key.get(BASELINE_HOOKS_KEY, {}), BASELINE_HOOKS_KEY)
    return (
        {
            str(each_path): _parse_baseline_entry(each_entry)
            for each_path, each_entry in raw_files.items()
        },
        {
            str(each_name): _integer(each_count, BASELINE_HOOKS_KEY)
            for each_name, each_count in raw_hooks.items()
        },
    )


def _json_object(policy_text: str) -> dict:
    try:
        raw_policy = json.loads(policy_text)
    except json.JSONDecodeError as error:
        raise ContextBudgetPolicyError(str(error)) from error
    if not isinstance(raw_policy, dict):
        raise ContextBudgetPolicyError(POLICY_ERROR_NOT_OBJECT)
    return raw_policy


def parse_policy(policy_text: str) -> BudgetPolicy:
    """Parse policy JSON text; unknown keys are ignored.

    Args:
        policy_text: The text of ``.claude/context-budget.json``.

    Returns:
        The parsed policy.

    Raises:
        ContextBudgetPolicyError: When the text is not JSON of the documented shape.
    """
    raw_policy = _json_object(policy_text)
    entry_by_path, characters_by_hook_name = _parse_baseline(raw_policy.get(BASELINE_KEY, {}))
    return BudgetPolicy(
        section_detail_line_limit=_integer(
            raw_policy.get(SECTION_DETAIL_LINE_LIMIT_KEY, DEFAULT_SECTION_DETAIL_LINE_LIMIT),
            SECTION_DETAIL_LINE_LIMIT_KEY,
        ),
        all_kinds=tuple(
            _parse_kind(each) for each in _items(raw_policy.get(KINDS_KEY, []), KINDS_KEY)
        ),
        all_hooks=tuple(
            _parse_hook(each) for each in _items(raw_policy.get(HOOKS_KEY, []), HOOKS_KEY)
        ),
        baseline_entry_by_path=entry_by_path,
        baseline_characters_by_hook_name=characters_by_hook_name,
    )


def find_repository_root(file_path: Path) -> Path | None:
    """Return the nearest ancestor holding a ``.git`` file or directory.

    Args:
        file_path: Absolute path of a file that may not exist yet.

    Returns:
        The repository root, or None outside any repository.
    """
    for each_directory in file_path.parents:
        if (each_directory / GIT_MARKER_NAME).exists():
            return each_directory
    return None


def read_policy_file(repository_root: Path) -> BudgetPolicy | None:
    """Read and parse a repository's policy file.

    Args:
        repository_root: Repository root directory.

    Returns:
        The parsed policy, or None when the repository has no policy file.

    Raises:
        ContextBudgetPolicyError: When the file exists and does not parse.
    """
    policy_path = repository_root.joinpath(*ALL_POLICY_PATH_PARTS)
    try:
        policy_text = policy_path.read_text(encoding=UTF8_ENCODING)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        raise ContextBudgetPolicyError(str(error)) from error
    return parse_policy(policy_text)
