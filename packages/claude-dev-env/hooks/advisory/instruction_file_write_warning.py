#!/usr/bin/env python3
"""PostToolUse warning: a written instruction file breaks the budget, names a person, or nests too deep.

This hook never blocks. It runs after each Write, Edit, or MultiEdit. When the
file is an instruction file, a file a launch file imports, any other markdown
file a link can pass through, or the budget file itself, in a repository that
has ``instruction-budget.json``, it runs the same checks the CI workflow runs and
adds one line per finding to the agent's context::

    AGENTS.md: [instruction-nesting] is 3 link hops from an entry file, over the cap of 2. ...

Quiet paths: a file that is not markdown, not the budget file, and not loaded
as instructions, a repository without the budget file, a budget file that holds no
valid limits, a read error during the check, a file that passes every check, and
a budget finding on a file the launch total leaves out each emit nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parents[1])
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

_scripts_directory = str(Path(__file__).resolve().parents[2] / "scripts")
if _scripts_directory not in sys.path:
    sys.path.insert(0, _scripts_directory)

from dev_env_scripts_constants.followup_constants import INSTRUCTION_BUDGET_RULE_ID
from dev_env_scripts_constants.instruction_budget_constants import (
    INSTRUCTION_BUDGET_CONFIG_FILE_NAME,
    MARKDOWN_SUFFIX,
)
from hooks_constants.instruction_file_write_warning_constants import (
    CONTEXT_HEADER_TEMPLATE,
    CONTEXT_LINE_SEPARATOR,
    FILE_PATH_KEY,
    TOOL_INPUT_KEY,
)
from hooks_constants.post_tool_use_context import write_post_tool_use_context_to_stdout
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from instruction_budget import check_repository, finding_line
from instruction_budget_files import (
    InstructionBudgetConfig,
    InstructionBudgetConfigError,
    InstructionFinding,
    is_instruction_file,
    launch_files,
    load_config,
)


def _written_path(payload: dict | None) -> Path | None:
    if not isinstance(payload, dict):
        return None
    tool_input = payload.get(TOOL_INPUT_KEY)
    if not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get(FILE_PATH_KEY)
    if not isinstance(file_path, str) or not file_path:
        return None
    return Path(file_path).resolve()


def _repository_root(written_path: Path) -> Path | None:
    for each_directory in written_path.parents:
        if (each_directory / INSTRUCTION_BUDGET_CONFIG_FILE_NAME).is_file():
            return each_directory
    return None


def _findings_for(
    repository_root: Path, written_path: Path, config: InstructionBudgetConfig
) -> list[InstructionFinding]:
    try:
        is_launch_file = written_path in launch_files(repository_root, config)
        if (
            not is_launch_file
            and not is_instruction_file(written_path, repository_root, config)
            and written_path.suffix != MARKDOWN_SUFFIX
            and written_path.name != INSTRUCTION_BUDGET_CONFIG_FILE_NAME
        ):
            return []
        all_findings = check_repository(repository_root, config, [written_path])
    except (OSError, ValueError, RecursionError):
        return []
    return [
        each_finding
        for each_finding in all_findings
        if each_finding.rule_id != INSTRUCTION_BUDGET_RULE_ID or is_launch_file
    ]


def main() -> None:
    written_path = _written_path(read_hook_input_dictionary_from_stdin())
    if written_path is None:
        return
    repository_root = _repository_root(written_path)
    if repository_root is None:
        return
    try:
        config = load_config(repository_root)
    except InstructionBudgetConfigError:
        return
    if config is None:
        return
    all_findings = _findings_for(repository_root, written_path, config)
    if not all_findings:
        return
    all_lines = [
        CONTEXT_HEADER_TEMPLATE.format(
            file_path=written_path.relative_to(repository_root).as_posix()
        )
    ] + [finding_line(each_finding) for each_finding in all_findings]
    write_post_tool_use_context_to_stdout(CONTEXT_LINE_SEPARATOR.join(all_lines))


if __name__ == "__main__":
    main()
