"""Constants for the role-stack retirement inventory."""

from __future__ import annotations

UTF8_ENCODING: str = "utf-8"
MANIFEST_RELATIVE_PATH: str = "rules-archived/ARCHIVE-MANIFEST.md"
ROLE_STACK_SECTION_HEADING: str = "## Role stack replacements"
ROLE_STACK_SKILL_RELATIVE_PATH: str = ".agents/skills/role-stack/SKILL.md"
EVAL_GUIDE_PATH_SUFFIX: str = "features-start-with-an-eval.md"
FIRST_ACTION_BEHAVIOR_PREFIX: str = "Your first action is the Skill tool"
RETIRED_PATH_HEADER: str = "retired path"
PATH_NONE: str = "none"
REQUIREMENT_NONE: str = "none"
REPRODUCIBLE_CHECK_SENTENCE: str = (
    "A reproducible, re-runnable check is still required before any done claim."
)
FIRST_ACTION_RETIRED_SENTENCE: str = (
    "Only the forced position as the very first action is retired."
)
ALL_TRUST_CARD_LINES: tuple[str, ...] = (
    "Red before the fix",
    "wrong twin fails",
    "undo fails again",
)
ALL_EVAL_OPTIONAL_MARKERS: tuple[str, ...] = (
    "evals are optional",
    "eval is optional",
    "evals optional",
    "optional eval",
    "reproducible check is removed",
    "reproducible check is retired",
    "no reproducible check",
    "without a reproducible check",
)
FINDING_BEHAVIOR_STILL_ACTIVE: str = "behavior-still-active"
FINDING_TRIGGER_MISSING: str = "trigger-missing"
FINDING_MARKS_EVALS_OPTIONAL: str = "marks-evals-optional"
FINDING_DROPS_REPRODUCIBLE_CHECK: str = "drops-reproducible-check"
FINDING_DROPS_TRUST_LINE: str = "drops-trust-line"
FINDING_DROPS_FIRST_ACTION_NOTE: str = "drops-first-action-retired-note"
