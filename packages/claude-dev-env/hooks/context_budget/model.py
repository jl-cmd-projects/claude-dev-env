"""Frozen data shapes of the context budget check.

::

    BudgetPolicy
      kinds     ContextKind("skill entry", ("**/SKILL.md",), 200, True)
      hooks     HookBudget("startup print", ("python3", "x.py"), "{}", 1500)
      baseline  {"a/SKILL.md": BaselineEntry(743, ("Plan",))}, {"startup print": 5200}
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


class ContextBudgetPolicyError(ValueError):
    """Raised when a policy file does not match the documented shape."""


@dataclass(frozen=True)
class ContextKind:
    """One row of the kind table.

    Attributes:
        name: Kind name used in messages.
        all_patterns: Globs over repository-relative POSIX paths.
        line_limit: Physical line limit, or None for a skipped kind.
        is_section_rule_on: Whether the section rule applies.
    """

    name: str
    all_patterns: tuple[str, ...]
    line_limit: int | None
    is_section_rule_on: bool


@dataclass(frozen=True)
class HookBudget:
    """One context-adding hook and its character limit.

    Attributes:
        name: Hook name, the key of its baseline number.
        all_command_parts: Argument vector run from the repository root.
        stdin_text: JSON text written to the hook's standard input.
        char_limit: Injected character limit.
    """

    name: str
    all_command_parts: tuple[str, ...]
    stdin_text: str
    char_limit: int


@dataclass(frozen=True)
class BaselineEntry:
    """The recorded over-budget state of one file.

    Attributes:
        lines: Recorded physical line count.
        all_section_headings: Over-limit unpointed section headings, a multiset.
    """

    lines: int
    all_section_headings: tuple[str, ...]


@dataclass(frozen=True)
class BudgetPolicy:
    """A parsed ``.claude/context-budget.json``.

    Attributes:
        section_detail_line_limit: Detail lines a section may hold without a pointer.
        all_kinds: Ordered kind table; the first matching kind wins.
        all_hooks: Context-adding hooks to measure.
        baseline_entry_by_path: Over-budget files by repository-relative path.
        baseline_characters_by_hook_name: Over-budget hooks by name.
    """

    section_detail_line_limit: int
    all_kinds: tuple[ContextKind, ...]
    all_hooks: tuple[HookBudget, ...] = ()
    baseline_entry_by_path: Mapping[str, BaselineEntry] = field(default_factory=dict)
    baseline_characters_by_hook_name: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SectionScan:
    """One Markdown section's measurements.

    Attributes:
        heading: Heading text, or ``(top)`` for lines before the first heading.
        detail_line_count: Detail lines in the section body.
        has_pointer: Whether the body links to a relative target.
    """

    heading: str
    detail_line_count: int
    has_pointer: bool


@dataclass(frozen=True)
class FileMeasure:
    """One context file measured against its kind.

    Attributes:
        kind: The kind the path matched.
        line_count: Physical lines, frontmatter included.
        all_over_limit_sections: Unpointed sections over the detail limit.
    """

    kind: ContextKind
    line_count: int
    all_over_limit_sections: tuple[SectionScan, ...]


@dataclass(frozen=True)
class BudgetFinding:
    """One budget violation.

    Attributes:
        path: Repository-relative path the finding names.
        scope: A section heading, or ``file`` for a whole-file finding.
        message: The full message with its fix.
    """

    path: str
    scope: str
    message: str
