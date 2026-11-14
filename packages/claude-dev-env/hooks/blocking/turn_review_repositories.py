"""Find the checkouts that take part in the turn review gate.

A repository takes part when it is the session's project folder or a folder
directly inside it, and its GitHub origin ``owner/repo`` slug is listed in
``CLAUDE_TURN_REVIEW_REPOSITORIES``::

    project folder /work, listed slugs "Owner/App, owner/lib"
        /work/app   origin owner/app    ->  takes part
        /work/docs  origin owner/docs   ->  left out
        /work/notes no .git entry       ->  left out

The listed slugs are compared without regard to letter case. A folder that
cannot be read is left out.
"""

from __future__ import annotations

import os
from pathlib import Path

from hooks_constants.turn_review_gate_constants import (
    GIT_DIRECTORY_NAME,
    PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE,
    REPOSITORIES_ENVIRONMENT_VARIABLE,
    REPOSITORY_SEPARATOR,
)
from pii_prevention_blocker_parts.repository_exemption import repository_origin_slug


def _opted_in_repository_slugs() -> frozenset[str]:
    listed = os.environ.get(REPOSITORIES_ENVIRONMENT_VARIABLE, "")
    return frozenset(
        each.strip().casefold() for each in listed.split(REPOSITORY_SEPARATOR) if each.strip()
    )


def _opted_in_repository_roots(all_slugs: frozenset[str]) -> list[Path]:
    project_directory = os.environ.get(PROJECT_DIRECTORY_ENVIRONMENT_VARIABLE, "")
    if not project_directory or not Path(project_directory).is_dir():
        return []
    project_path = Path(project_directory).resolve()
    all_candidates = [project_path, *sorted(_child_entries(project_path))]
    return [each for each in all_candidates if _is_opted_in_checkout(each, all_slugs)]


def _child_entries(project_path: Path) -> list[Path]:
    try:
        return list(project_path.iterdir())
    except OSError:
        return []


def _is_opted_in_checkout(folder: Path, all_slugs: frozenset[str]) -> bool:
    try:
        is_checkout = folder.is_dir() and (folder / GIT_DIRECTORY_NAME).exists()
    except OSError:
        return False
    return is_checkout and repository_origin_slug(folder) in all_slugs
