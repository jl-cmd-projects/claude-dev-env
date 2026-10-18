"""Build the Claude or Codex command for one review."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from tools import review_profile
from tools.config import review_run_constants as c


def review_system_prompt(rules_text: str) -> str:
    """Return the system prompt text a Claude-compatible review receives.

    Args:
        rules_text: The review rules.

    Returns:
        The system prompt text.
    """
    return c.REVIEW_RULES_SYSTEM_TEMPLATE.format(
        separator=c.PROMPT_SECTION_SEPARATOR, rules=rules_text
    )


def write_system_prompt(
    destination: Path,
    system_text: str,
    profile: review_profile.ReviewProfile | None = None,
) -> Path:
    """Write the system prompt, then the profile's code standards, into one file.

    Args:
        destination: The file that receives the prompt.
        system_text: The rules prompt.
        profile: The slim profile, when one was built.

    Returns:
        The destination path.
    """
    all_parts = [system_text]
    if profile is not None:
        all_parts.append(
            profile.standards_path.read_text(encoding=c.TEXT_ENCODING).strip()
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        c.PROMPT_SECTION_SEPARATOR.join(all_parts), encoding=c.TEXT_ENCODING
    )
    return destination


def review_command(
    harness: str,
    model: str,
    effort: str,
    level: str,
    rules_text: str,
    executable: str,
    review_diff: str | None = None,
    advisor: str = "none",
    all_profile_arguments: Sequence[str] = (),
    system_prompt_path: Path | None = None,
) -> tuple[list[str], str]:
    """Return the review command and the text it reads on standard input.

    Args:
        harness: claude, codex, or third_party.
        model: The model family or resolved slug.
        effort: The reasoning effort.
        level: The review level a slash command takes.
        rules_text: The review rules a Codex review receives on standard input.
        executable: The agent executable to launch.
        review_diff: Candidate diff supplied to a Claude-compatible review.
        advisor: The Claude advisor model, or none.
        all_profile_arguments: Review profile arguments for a Claude review.
        system_prompt_path: A file that holds the system prompt.

    Returns:
        The argument list and the standard input text.
    """
    return _assembled_review_command(harness, model, effort, level, rules_text, executable, review_diff, advisor, all_profile_arguments, system_prompt_path)


def _assembled_review_command(
    harness: str,
    model: str,
    effort: str,
    level: str,
    rules_text: str,
    executable: str,
    review_diff: str | None,
    advisor: str,
    all_profile_arguments: Sequence[str],
    system_prompt_path: Path | None,
) -> tuple[list[str], str]:
    if harness == c.HARNESS_CODEX:
        return _codex_review_command(executable, model, effort, rules_text)
    command = [
        *_claude_agent_arguments(executable, model, effort),
        *review_profile.advisor_options(advisor)[0],
        *_system_prompt_arguments(review_system_prompt(rules_text), system_prompt_path),
        *_review_isolation_arguments(harness, all_profile_arguments),
    ]
    return command, _claude_review_prompt(harness, level, review_diff)


def _codex_review_command(
    executable: str, model: str, effort: str, rules_text: str
) -> tuple[list[str], str]:
    prompt = c.PROMPT_SECTION_SEPARATOR.join(
        [
            c.CODEX_BASE_BRANCH_PROMPT_TEMPLATE.format(base_branch=c.BASE_BRANCH),
            rules_text,
        ]
    )
    return [executable, "review", *_codex_options(model, effort)], prompt


def _claude_agent_arguments(executable: str, model: str, effort: str) -> list[str]:
    return [
        executable,
        "-p",
        "--model",
        model,
        "--effort",
        effort,
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        c.CLAUDE_PERMISSION_MODE,
    ]


def _system_prompt_arguments(
    system_text: str, system_prompt_path: Path | None
) -> list[str]:
    if system_prompt_path is None:
        return ["--append-system-prompt", system_text]
    return ["--append-system-prompt-file", str(system_prompt_path)]


def _review_isolation_arguments(
    harness: str, all_profile_arguments: Sequence[str]
) -> list[str]:
    all_arguments = [
        "--restricted",
        "--tools",
        c.TOOL_LIST_SEPARATOR.join(_review_tools(harness)),
    ]
    _extend_profile_arguments(all_arguments, harness, all_profile_arguments)
    if harness == c.HARNESS_THIRD_PARTY:
        all_arguments.extend(["--disallowedTools", *c.ALL_THIRD_PARTY_DISALLOWED_TOOLS])
    return all_arguments


def _review_tools(harness: str) -> tuple[str, ...]:
    if harness == c.HARNESS_THIRD_PARTY:
        return c.ALL_THIRD_PARTY_REVIEW_TOOLS
    return c.ALL_CLAUDE_REVIEW_TOOLS


def _extend_profile_arguments(
    all_arguments: list[str], harness: str, all_profile_arguments: Sequence[str]
) -> None:
    if harness == c.HARNESS_CLAUDE and all_profile_arguments:
        all_arguments.extend(all_profile_arguments)
        return
    all_arguments.extend(_no_mcp_settings_arguments())


def _no_mcp_settings_arguments() -> list[str]:
    all_settings = {"permissions": {"blockReadsOutsideWorkingDirectories": True}}
    return [
        "--strict-mcp-config",
        "--mcp-config",
        c.EMPTY_MCP_CONFIG,
        "--settings",
        json.dumps(all_settings),
    ]


def _claude_review_prompt(harness: str, level: str, review_diff: str | None) -> str:
    prompt = "/code-review {level} {base_branch}".format(
        level=level, base_branch=c.BASE_BRANCH
    )
    if harness != c.HARNESS_CLAUDE:
        prompt = "/e-code-review {level} {base_branch}".format(
            level=level, base_branch=c.BASE_BRANCH
        )
    if review_diff is not None:
        prompt += c.CLAUDE_REVIEW_DIFF_PROMPT_TEMPLATE.format(diff=review_diff)
    return prompt


def _codex_options(model: str, effort: str) -> list[str]:
    return [
        "--strict-config",
        "-c",
        c.CODEX_MODEL_ASSIGNMENT_TEMPLATE.format(model=model),
        "-c",
        c.CODEX_EFFORT_ASSIGNMENT_TEMPLATE.format(effort=effort),
        "-c",
        c.CODEX_NO_MCP_SERVERS_ASSIGNMENT,
        *_disabled_feature_arguments(),
        c.CODEX_STDIN_PROMPT,
    ]


def _disabled_feature_arguments() -> list[str]:
    all_arguments: list[str] = []
    for each_feature in c.ALL_CODEX_DISABLED_FEATURES:
        all_arguments.extend(("--disable", each_feature))
    return all_arguments
