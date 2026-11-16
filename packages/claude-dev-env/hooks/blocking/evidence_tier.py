"""Choose the evidence a new pull request owes from the paths it changes.

A live proof is for behavior a test process cannot reproduce. The tier says
how much proof the pull request gate asks for::

    none     every changed path is a doc or a test, and none is a live surface
    checked  code changed, and no changed path is a live surface
    live     a changed path is a live surface, the file list is unread, the
             command runs more than the pull request call, or an edit names
             its pull request

A live surface is an agent surface, a file under .github/, a page people see, the
live-surfaces file itself, or a path a glob in the base branch's
``.claude/live-surfaces.txt`` names, unless that path is a test. When the
base has no such file, every path that is not a doc or a test is a live
surface.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from collections.abc import Sequence
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import NamedTuple

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from hooks_constants.evidence_tier_constants import (
    ALL_AGENT_SURFACE_DIRECTORY_NAMES,
    ALL_AGENT_SURFACE_FILE_NAME_GLOBS,
    ALL_AGENT_SURFACE_FILE_NAMES,
    ALL_CODE_TEXT_FILE_NAME_GLOBS,
    ALL_DOCS_DATA_EXTENSIONS,
    ALL_DOCS_DIRECTORY_NAMES,
    ALL_DOCS_EXTENSIONS,
    ALL_GLOB_CHARACTERS,
    ALL_TEST_DIRECTORY_NAMES,
    ALL_TEST_FILE_INFIXES,
    ALL_TEST_FILE_NAMES,
    ALL_TEST_FILE_PREFIXES,
    ALL_TEST_FILE_SUFFIXES,
    BYTE_ORDER_MARK,
    FOLDER_GLOB_SUFFIX,
    LIVE_SURFACES_COMMENT_MARKER,
    LIVE_SURFACES_FILE_PATH,
    GITHUB_DIRECTORY_NAME,
    TRAILING_COMMENT_PATTERN,
    UNDECODABLE_BYTE_MARK,
)
from hooks_constants.pull_request_proof_constants import ALL_VISIBLE_FILE_SUFFIXES


class EvidenceTier(Enum):
    """How much proof a new pull request owes."""

    NONE = "none"
    CHECKED = "checked"
    LIVE = "live"


class TierCause(Enum):
    """Why the changed paths gave a tier; each cause belongs to one tier."""

    ONLY_DOCS_AND_TESTS = ("only docs and tests", EvidenceTier.NONE)
    CODE_WITHOUT_LIVE_SURFACE = ("code without a live surface", EvidenceTier.CHECKED)
    LIVE_SURFACE = ("a live surface", EvidenceTier.LIVE)
    NO_DECLARED_SURFACES = ("code with no declared surfaces", EvidenceTier.LIVE)
    UNREAD_FILE_LIST = ("an unread file list", EvidenceTier.LIVE)
    SHARED_COMMAND = ("a command that runs more than the pull request call", EvidenceTier.LIVE)
    NAMED_PULL_REQUEST_EDIT = ("an edit that names its pull request", EvidenceTier.LIVE)

    @property
    def tier(self) -> EvidenceTier:
        """Return the tier this cause gives."""
        return self.value[1]


class TierChoice(NamedTuple):
    """The cause of a pull request's tier and the changed path that decided it.

    ::

        TierChoice(LIVE_SURFACE, "skills/x/SKILL.md")      the first live surface
        TierChoice(NO_DECLARED_SURFACES, "src/gate.py")    the first code path
        TierChoice(CODE_WITHOUT_LIVE_SURFACE, "src/a.py")  the first code path
        TierChoice(ONLY_DOCS_AND_TESTS, None)
        TierChoice(UNREAD_FILE_LIST, None)
        TierChoice(SHARED_COMMAND, None)
        TierChoice(NAMED_PULL_REQUEST_EDIT, None)
    """

    cause: TierCause
    deciding_path: str | None

    @property
    def tier(self) -> EvidenceTier:
        """Return the tier the cause gives."""
        return self.cause.tier


def is_docs_or_test_path(repository_path: str) -> bool:
    """Return whether a repository path is a doc, a data file under a docs folder, or a test.

    ::

        README.md, art/logo.png, docs/table.json       -> True
        tests/x.py, src/test_x.py, a.spec.ts, conftest.py -> True
        src/gate.py, data/table.json                   -> False
        requirements-dev.txt, constraints.txt          -> False

    A requirements or constraints file ends in .txt, and it is code: it sets
    what gets installed. Its name matches in any case.

    Args:
        repository_path: A path relative to the repository root, with forward slashes.
    """
    path = PurePosixPath(repository_path)
    if any(fnmatch.fnmatchcase(path.name.lower(), each_glob) for each_glob in ALL_CODE_TEXT_FILE_NAME_GLOBS):
        return is_test_path(repository_path)
    if path.suffix.lower() in ALL_DOCS_EXTENSIONS:
        return True
    if path.suffix.lower() in ALL_DOCS_DATA_EXTENSIONS and any(
        each_part in ALL_DOCS_DIRECTORY_NAMES for each_part in path.parts[:-1]
    ):
        return True
    return is_test_path(repository_path)


def is_test_path(repository_path: str) -> bool:
    """Return whether a repository path is a test file or sits under a test folder.

    ::

        tests/x.py, src/test_x.py, src/x_test.py, a.spec.ts, bin/a.test.js, conftest.py -> True
        README.md, docs/table.json, src/gate.py                                        -> False

    Args:
        repository_path: A path relative to the repository root, with forward slashes.
    """
    path = PurePosixPath(repository_path)
    if path.name in ALL_TEST_FILE_NAMES:
        return True
    if any(each_part in ALL_TEST_DIRECTORY_NAMES for each_part in path.parts[:-1]):
        return True
    return (
        path.name.startswith(ALL_TEST_FILE_PREFIXES)
        or path.name.endswith(ALL_TEST_FILE_SUFFIXES)
        or any(each_infix in path.name for each_infix in ALL_TEST_FILE_INFIXES)
    )


def declared_live_surface_globs(surfaces_file_text: str) -> tuple[str, ...] | None:
    """Return the globs a live-surfaces file declares, one per line, or None for a file that is not UTF-8.

    ::

        "# prose agents read\\ndocs/rule-guides/\\n\\nportal/*.py\\n" -> ("docs/rule-guides/", "portal/*.py")
        "portal/  # seller portal\\n"                            -> ("portal/",)
        "\\ufeffsrc/\\n"                                          -> ("src/",)
        text that holds a U+FFFD replacement character          -> None

    A line that starts with '#' after its indent is a comment. A '#' after a
    space or a tab starts a comment that runs to the end of the line; a '#'
    inside a glob, as in lib/c#/x.py, stays. Blank lines are
    skipped. A leading byte order mark is dropped. A replacement character
    marks bytes that did not decode as UTF-8, so the file declares nothing and
    code stays live.

    Args:
        surfaces_file_text: The text of the base branch's live-surfaces file.
    """
    if UNDECODABLE_BYTE_MARK in surfaces_file_text:
        return None
    all_stripped_lines = (
        re.split(TRAILING_COMMENT_PATTERN, each_line, maxsplit=1)[0].strip()
        for each_line in surfaces_file_text.removeprefix(BYTE_ORDER_MARK).splitlines()
    )
    return tuple(
        each_line
        for each_line in all_stripped_lines
        if each_line and not each_line.startswith(LIVE_SURFACES_COMMENT_MARKER)
    )


def _is_agent_surface(repository_path: str) -> bool:
    path = PurePosixPath(repository_path.lower())
    if path.name in ALL_AGENT_SURFACE_FILE_NAMES:
        return True
    if any(
        fnmatch.fnmatchcase(path.name, each_glob) for each_glob in ALL_AGENT_SURFACE_FILE_NAME_GLOBS
    ):
        return True
    return any(each_part in ALL_AGENT_SURFACE_DIRECTORY_NAMES for each_part in path.parts[:-1])


def _is_github_file(repository_path: str) -> bool:
    return GITHUB_DIRECTORY_NAME in PurePosixPath(repository_path).parts[:-1]


def _matches_declared_glob(repository_path: str, declared_glob: str) -> bool:
    if declared_glob.endswith(FOLDER_GLOB_SUFFIX):
        return repository_path.startswith(declared_glob)
    if not any(each_character in declared_glob for each_character in ALL_GLOB_CHARACTERS):
        return repository_path == declared_glob or repository_path.startswith(declared_glob + FOLDER_GLOB_SUFFIX)
    return fnmatch.fnmatchcase(repository_path, declared_glob)


def _is_built_in_live_surface(repository_path: str) -> bool:
    return (
        repository_path == LIVE_SURFACES_FILE_PATH
        or _is_agent_surface(repository_path)
        or _is_github_file(repository_path)
        or repository_path.lower().endswith(ALL_VISIBLE_FILE_SUFFIXES)
    )


def _is_live_surface(repository_path: str, all_declared_globs: Sequence[str]) -> bool:
    if _is_built_in_live_surface(repository_path):
        return True
    return not is_test_path(repository_path) and any(
        _matches_declared_glob(repository_path, each_glob) for each_glob in all_declared_globs
    )


def choose_tier(
    all_changed_paths: Sequence[str] | None, all_declared_globs: Sequence[str] | None
) -> TierChoice:
    """Return the tier a pull request's changed paths give it, with the path that decided it.

    ::

        ["README.md", "tests/test_x.py"], globs       -> ONLY_DOCS_AND_TESTS, None
        ["README.md", "src/gate.py"], globs no match  -> CODE_WITHOUT_LIVE_SURFACE, "src/gate.py"
        ["src/gate.py"], None                         -> NO_DECLARED_SURFACES, "src/gate.py"
        ["src/gate.py", "skills/x/SKILL.md"], globs   -> LIVE_SURFACE, "skills/x/SKILL.md"
        None or []                                    -> UNREAD_FILE_LIST, None

    A glob that ends in '/' matches every path under that folder. A line with
    no '*', '?' or '[' matches that exact path, or every path under it as a
    folder. Any other glob matches the whole path with fnmatch, where '*'
    crosses folders. A declared glob never makes a test path live, as
    is_test_path reads one; a built-in live surface, such as a test under
    skills/, stays live.

    Args:
        all_changed_paths: Every path the pull request adds, edits, deletes or moves
            from or to, or None when the list could not be read in full.
        all_declared_globs: The base branch's declared globs, or None when the base
            gives no readable live-surfaces file.
    """
    if not all_changed_paths:
        return TierChoice(TierCause.UNREAD_FILE_LIST, None)
    live_path = next(
        (
            each_path
            for each_path in all_changed_paths
            if _is_live_surface(each_path, all_declared_globs or ())
        ),
        None,
    )
    if live_path is not None:
        return TierChoice(TierCause.LIVE_SURFACE, live_path)
    code_path = next(
        (each_path for each_path in all_changed_paths if not is_docs_or_test_path(each_path)), None
    )
    if code_path is None:
        return TierChoice(TierCause.ONLY_DOCS_AND_TESTS, None)
    if all_declared_globs is None:
        return TierChoice(TierCause.NO_DECLARED_SURFACES, code_path)
    return TierChoice(TierCause.CODE_WITHOUT_LIVE_SURFACE, code_path)


def first_agent_surface_path(all_changed_paths: Sequence[str]) -> str | None:
    """Return the first changed path an agent reads as instructions or settings, or None.

    ::

        ["src/a.py", "rules/x.md", "SKILL.md"]         -> "rules/x.md"
        ["src/a.py", ".github/workflows/ci.yml"]        -> None

    An agent surface is a SKILL.md, AGENTS.md, CLAUDE.md, CLAUDE.local.md,
    copilot-instructions.md, hooks.json, .mcp.json or settings*.json file, or
    a file under a skills, rules, agents, commands, system-prompts,
    system_prompts or output-styles folder. Names match in any case, so
    Skills/x/skill.md counts.

    Args:
        all_changed_paths: Every path the pull request changes.
    """
    return next(
        (each_path for each_path in all_changed_paths if _is_agent_surface(each_path)), None
    )
