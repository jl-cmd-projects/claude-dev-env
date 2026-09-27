from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from local_report_core import PublicationOutcome, publish_local_report
from local_verification.config import SUCCESS_EXIT_CODE
from pr_verification.config.constants import GIT_BARE_SUFFIX, GITHUB_API_URL
from pr_verification.github import GitHubApi, GitHubAppAuthenticator, GitHubError
from pr_verification.model import RepositorySettings


def main(
    all_arguments: Sequence[str],
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Publish one local verification report.

    Args:
        all_arguments: Command line arguments.
        stdout: Output stream for the publication outcome.
        stderr: Output stream for startup and API errors.

    Returns:
        The verifier process exit code.
    """
    parser = _build_parser()
    parsed_arguments = parser.parse_args(list(all_arguments))
    try:
        outcome = _publish_from_arguments(parsed_arguments)
    except (OSError, TypeError, ValueError, GitHubError) as error:
        stderr.write(f"{error}\n")
        return 3
    stdout.write(json.dumps(_outcome_mapping(outcome)) + "\n")
    return SUCCESS_EXIT_CODE


def _publish_from_arguments(parsed_arguments: argparse.Namespace) -> PublicationOutcome:
    all_settings = _read_settings_file(parsed_arguments.settings)
    api_url = _required_setting(
        parsed_arguments.api_url, all_settings, "api_url", GITHUB_API_URL
    )
    repository_slug = _required_repository_setting(
        parsed_arguments.repository, all_settings
    )
    pull_request_number = _required_integer_setting(
        parsed_arguments.pull_number, all_settings, "pull_number"
    )
    repository = RepositorySettings(repository_slug, repository_slug + GIT_BARE_SUFFIX)
    github = _issue_repository_api(parsed_arguments, all_settings, api_url, repository)
    return publish_local_report(
        github,
        repository,
        pull_request_number,
        parsed_arguments.local_repo,
        parsed_arguments.manifest,
        parsed_arguments.report,
    )


def _issue_repository_api(
    parsed_arguments: argparse.Namespace,
    all_settings: Mapping[str, object],
    api_url: str,
    repository: RepositorySettings,
) -> GitHubApi:
    if parsed_arguments.token_environment is not None:
        return GitHubApi(api_url, _environment_token(parsed_arguments.token_environment))
    authenticator = GitHubAppAuthenticator(
        api_url,
        _required_integer_setting(parsed_arguments.app_id, all_settings, "app_id"),
        _required_integer_setting(
            parsed_arguments.installation_id, all_settings, "installation_id"
        ),
        _required_path_setting(parsed_arguments.private_key_path, all_settings),
    )
    return authenticator.issue_repository_api(
        repository, should_write_issue_labels=True
    )


def _environment_token(variable_name: str) -> str:
    token = os.environ.get(variable_name)
    if not token:
        raise TypeError(f"Missing publisher token in environment variable: {variable_name}")
    return token


def _outcome_mapping(outcome: PublicationOutcome) -> dict[str, object]:
    return {
        "status": outcome.status.value,
        "description": outcome.description,
        "publishable": outcome.publishable,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cde publish-local-report")
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--api-url")
    parser.add_argument("--app-id", type=int)
    parser.add_argument("--installation-id", type=int)
    parser.add_argument("--private-key-path", type=Path)
    parser.add_argument("--token-environment")
    parser.add_argument("--repository")
    parser.add_argument("--pull-number", type=int)
    parser.add_argument("--local-repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def _read_settings_file(settings_path: Path | None) -> Mapping[str, object]:
    if settings_path is None:
        return {}
    parsed_settings = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(parsed_settings, Mapping):
        raise ValueError("Publisher settings must be an object")
    return parsed_settings


def _required_setting(
    explicit_setting: object,
    all_settings: Mapping[str, object],
    setting_name: str,
    default_setting: str | None = None,
) -> str:
    selected_setting = explicit_setting
    if selected_setting is None:
        selected_setting = all_settings.get(setting_name, default_setting)
    if not isinstance(selected_setting, str) or not selected_setting:
        raise TypeError(f"Missing publisher setting: {setting_name}")
    return selected_setting


def _required_repository_setting(
    explicit_repository: object, all_settings: Mapping[str, object]
) -> str:
    repository_slug = _required_setting(explicit_repository, all_settings, "repository")
    try:
        repository_owner, repository_name = repository_slug.split("/")
    except ValueError as error:
        raise TypeError("Repository must use the owner/name form") from error
    if not repository_owner or not repository_name:
        raise TypeError("Repository must use the owner/name form")
    return repository_slug


def _required_path_setting(
    explicit_path: object, all_settings: Mapping[str, object]
) -> Path:
    selected_path = explicit_path
    if selected_path is None:
        selected_path = all_settings.get("private_key_path")
    if not isinstance(selected_path, (str, Path)) or not selected_path:
        raise TypeError("Missing publisher setting: private_key_path")
    return Path(selected_path)


def _required_integer_setting(
    explicit_setting: object,
    all_settings: Mapping[str, object],
    setting_name: str,
) -> int:
    selected_setting = explicit_setting
    if selected_setting is None:
        selected_setting = all_settings.get(setting_name)
    if isinstance(selected_setting, bool) or not isinstance(selected_setting, int):
        raise TypeError(f"Missing publisher setting: {setting_name}")
    return selected_setting


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
