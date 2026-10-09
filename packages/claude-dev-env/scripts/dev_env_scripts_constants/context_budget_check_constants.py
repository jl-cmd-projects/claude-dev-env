"""Constants for the context budget command."""

from __future__ import annotations

COMMAND_DESCRIPTION = (
    "Check context files against .claude/context-budget.json, measure its hooks, "
    "or rebuild its over-budget list from the current tree."
)
PATHS_HELP = "Context files to check; the prior state is each file's HEAD version."
HOOKS_FLAG = "--hooks"
HOOKS_HELP = "Run each hook the policy lists and hold it to its character budget."
WRITE_BASELINE_FLAG = "--write-baseline"
WRITE_BASELINE_HELP = "Rebuild the policy's baseline from the tracked tree and its hooks."
HEAD_REVISION = "HEAD"
ALL_LS_FILES_ARGUMENTS: tuple[str, ...] = ("ls-files", "-z")
ALL_GIT_ROOT_ARGUMENTS: tuple[str, ...] = ("rev-parse", "--show-toplevel")
POLICY_RELATIVE_PATH = ".claude/context-budget.json"
MARKDOWN_SUFFIX = ".md"
UTF8_ENCODING = "utf-8"
NO_POLICY_MESSAGE = "context-budget: no " + POLICY_RELATIVE_PATH + " in this repository."
CLEAN_MESSAGE = "context-budget: OK ({count} checked)"
HOOK_REPORT_TEMPLATE = "{name}: {count} characters (limit {limit}, baseline {baseline})"
BASELINE_WRITTEN_MESSAGE = "context-budget: baseline written ({files} files, {hooks} hooks)"
NO_BASELINE_TEXT = "none"
FAILURE_EXIT_CODE = 1
SUCCESS_EXIT_CODE = 0
