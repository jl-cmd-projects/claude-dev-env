"""Resolve local identity values for the PII hooks.

The hooks ship into ``~/.claude/`` and cannot read a repository file, so they
read machine values from the environment or a git-ignored file in the Claude
home directory. This module supplies the NAS host the PII scanner allowlists
and the owner/repo slug set used by ``pii_exempt_repository_slugs``
(``CLAUDE_PII_EXEMPT_REPOS`` / ``pii_exempt_repositories``). The committed NAS
host default is a placeholder.

::

    CLAUDE_NAS_HOST set to a host              ->  nas_host() returns that host
    CLAUDE_PII_EXEMPT_REPOS="Owner/repo"       ->  {"owner/repo"}
    (env unset, no file)                       ->  nas_host() == "nas.example.local"
                                                   pii_exempt_repository_slugs() == frozenset()

Each value comes from its environment variable, then
``~/.claude/local-identity.json``, then the placeholder default (NAS only).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

NAS_HOST_ENV_VAR = "CLAUDE_NAS_HOST"
LOCAL_IDENTITY_PATH_ENV_VAR = "CLAUDE_LOCAL_IDENTITY_PATH"
PII_EXEMPT_REPOS_ENV_VAR = "CLAUDE_PII_EXEMPT_REPOS"
PII_EXEMPT_REPOS_JSON_KEY = "pii_exempt_repositories"
PII_EXEMPT_REPOS_SEPARATOR = ","
PII_ALLOWLISTED_VALUES_JSON_KEY = "pii_allowlisted_values"
NAS_JSON_KEY = "nas"
NAS_HOST_JSON_KEY = "host"
CLAUDE_HOME_DIRECTORY_NAME = ".claude"
LOCAL_IDENTITY_FILE_NAME = "local-identity.json"
PLACEHOLDER_NAS_HOST = "nas.example.local"


def _local_identity_file_path() -> Path:
    path_override = os.environ.get(LOCAL_IDENTITY_PATH_ENV_VAR)
    if path_override:
        return Path(path_override)
    return Path.home() / CLAUDE_HOME_DIRECTORY_NAME / LOCAL_IDENTITY_FILE_NAME


def _identity_dictionary_from_local_file() -> dict[str, object]:
    identity_path = _local_identity_file_path()
    if not identity_path.is_file():
        return {}
    try:
        parsed_identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return parsed_identity if isinstance(parsed_identity, dict) else {}


def _nas_section_from_local_file() -> dict[str, object]:
    nas_section = _identity_dictionary_from_local_file().get(NAS_JSON_KEY, {})
    return nas_section if isinstance(nas_section, dict) else {}


def _normalized_slug_set(all_raw_slugs: list[object]) -> frozenset[str]:
    return frozenset(
        each_slug.strip().lower()
        for each_slug in all_raw_slugs
        if isinstance(each_slug, str) and each_slug.strip()
    )


def _environment_exempt_slugs() -> frozenset[str]:
    """Return the exempt slugs named by ``CLAUDE_PII_EXEMPT_REPOS``, or empty."""
    slugs_from_environment = os.environ.get(PII_EXEMPT_REPOS_ENV_VAR)
    if slugs_from_environment is None:
        return frozenset()
    return _normalized_slug_set(
        list(slugs_from_environment.split(PII_EXEMPT_REPOS_SEPARATOR))
    )


def pii_exempt_repository_slugs() -> frozenset[str]:
    """Return owner/repo slugs whose commits skip the staged PII scan.

    ::

        CLAUDE_PII_EXEMPT_REPOS="Owner/repo-a, Other/b"  ->  {"owner/repo-a", "other/b"}
        (env unset, file lists ["Owner/repo-a"])         ->  {"owner/repo-a"}
        (env unset, no file)                             ->  frozenset()

    A non-empty environment variable (comma-separated) wins. When the variable
    is unset or normalizes to no slugs, the ``pii_exempt_repositories`` list in
    the git-ignored ``~/.claude/local-identity.json`` is used. Slugs are
    lowercased so matching is case-insensitive.

    Returns:
        Lowercased ``owner/repo`` slugs exempt from staged-commit PII scanning.
    """
    environment_slugs = _environment_exempt_slugs()
    if environment_slugs:
        return environment_slugs
    stored_slugs = _identity_dictionary_from_local_file().get(
        PII_EXEMPT_REPOS_JSON_KEY
    )
    if not isinstance(stored_slugs, list):
        return frozenset()
    return _normalized_slug_set(stored_slugs)


def _normalized_allowlisted_values(all_raw_values: object) -> frozenset[str]:
    """Return the non-empty string members of a raw values list, or empty."""
    if not isinstance(all_raw_values, list):
        return frozenset()
    return frozenset(
        each_value
        for each_value in all_raw_values
        if isinstance(each_value, str) and each_value
    )


def pii_allowlisted_values_by_repository() -> dict[str, frozenset[str]]:
    """Return the exact literal values each repository allows past the PII scan.

    ::

        file {"Owner/Repo": ["user@example.com"]}  ->  {"owner/repo": {"user@example.com"}}
        (env unset, no file, or bad json)          ->  {}

    Keyed by lowercased ``owner/repo`` slug so matching is case-insensitive; the
    values stay exact. The mapping lives under ``pii_allowlisted_values`` in the
    git-ignored ``~/.claude/local-identity.json`` so a private repository's real
    fixture addresses stay out of this published tree.

    Returns:
        Lowercased ``owner/repo`` slug to the frozenset of exact allowed values.
    """
    stored_mapping = _identity_dictionary_from_local_file().get(
        PII_ALLOWLISTED_VALUES_JSON_KEY
    )
    if not isinstance(stored_mapping, dict):
        return {}
    all_values_by_slug: dict[str, frozenset[str]] = {}
    for each_raw_slug, each_raw_values in stored_mapping.items():
        normalized_slug = each_raw_slug.strip().lower() if isinstance(each_raw_slug, str) else ""
        allowlisted_values = _normalized_allowlisted_values(each_raw_values)
        if normalized_slug and allowlisted_values:
            all_values_by_slug[normalized_slug] = allowlisted_values
    return all_values_by_slug


def nas_host() -> str:
    """Return the NAS host the ssh enforcer guards.

    ::

        CLAUDE_NAS_HOST set to a host  ->  that host
        (env unset, no file)           ->  "nas.example.local"

    The environment variable wins, then the git-ignored file, then the
    placeholder default.

    Returns:
        The NAS hostname or address.
    """
    host_from_environment = os.environ.get(NAS_HOST_ENV_VAR)
    if host_from_environment:
        return host_from_environment
    stored_host = _nas_section_from_local_file().get(NAS_HOST_JSON_KEY)
    if isinstance(stored_host, str) and stored_host:
        return stored_host
    return PLACEHOLDER_NAS_HOST
