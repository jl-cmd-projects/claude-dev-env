"""Probe Claude account usage meters for the account broker."""

from __future__ import annotations

import http.client
import importlib.util
import sys
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType

from dev_env_scripts_constants.claude_chain_usage_constants import (
    NO_ACCESS_TOKEN_ERROR_TEMPLATE,
    RESOLVE_USAGE_WINDOW_FILENAME,
    RESOLVE_USAGE_WINDOW_MISSING_ERROR_TEMPLATE,
    RESOLVE_USAGE_WINDOW_MODULE_NAME,
    USAGE_PAUSE_AGENTS_HOME_DIRECTORY_NAME,
    USAGE_PAUSE_SCRIPTS_DIRECTORY_NAME,
    USAGE_PAUSE_SKILL_DIRECTORY_NAME,
    USAGE_PAUSE_SKILL_NAME,
    USAGE_PROBE_FAILED_ERROR_TEMPLATE,
)


class WeeklyUtilizationProbeError(Exception):
    """Raised when an account's usage meters cannot be measured."""


def _usage_pause_scripts_directory() -> Path:
    package_root = Path(__file__).resolve().parent.parent
    return (
        package_root
        / USAGE_PAUSE_AGENTS_HOME_DIRECTORY_NAME
        / USAGE_PAUSE_SKILL_DIRECTORY_NAME
        / USAGE_PAUSE_SKILL_NAME
        / USAGE_PAUSE_SCRIPTS_DIRECTORY_NAME
    )


def _discard_sys_path_entry(path_text: str) -> None:
    if path_text in sys.path:
        sys.path.remove(path_text)


def _load_resolve_usage_window_module() -> ModuleType:
    already_loaded = sys.modules.get(RESOLVE_USAGE_WINDOW_MODULE_NAME)
    if already_loaded is not None:
        return already_loaded
    scripts_directory = _usage_pause_scripts_directory()
    module_path = scripts_directory / RESOLVE_USAGE_WINDOW_FILENAME
    if not module_path.is_file():
        raise WeeklyUtilizationProbeError(
            RESOLVE_USAGE_WINDOW_MISSING_ERROR_TEMPLATE.format(module_path=module_path)
        )
    scripts_directory_text = str(scripts_directory)
    was_path_inserted = False
    if scripts_directory_text not in sys.path:
        sys.path.insert(0, scripts_directory_text)
        was_path_inserted = True
    is_module_ready = False
    try:
        module_specification = importlib.util.spec_from_file_location(
            RESOLVE_USAGE_WINDOW_MODULE_NAME, module_path
        )
        if module_specification is None or module_specification.loader is None:
            raise WeeklyUtilizationProbeError(
                RESOLVE_USAGE_WINDOW_MISSING_ERROR_TEMPLATE.format(module_path=module_path)
            )
        loaded_module = importlib.util.module_from_spec(module_specification)
        sys.modules[RESOLVE_USAGE_WINDOW_MODULE_NAME] = loaded_module
        module_specification.loader.exec_module(loaded_module)
        is_module_ready = True
    finally:
        if not is_module_ready:
            sys.modules.pop(RESOLVE_USAGE_WINDOW_MODULE_NAME, None)
        if was_path_inserted:
            _discard_sys_path_entry(scripts_directory_text)
    return loaded_module


@dataclass(frozen=True)
class AccountUsageMeters:
    """An account's short and weekly utilization and reset times."""

    session_utilization: float | None
    session_resets_at: datetime | None
    weekly_utilization: float | None
    weekly_resets_at: datetime | None


def _fetch_account_usage_payload(
    usage_window_resolver: ModuleType, credentials_path: Path
) -> dict[str, object]:
    now = datetime.now().astimezone()
    try:
        access_token = usage_window_resolver.read_oauth_access_token(credentials_path, now)
        if access_token is None:
            raise WeeklyUtilizationProbeError(
                NO_ACCESS_TOKEN_ERROR_TEMPLATE.format(credentials_path=credentials_path)
            )
        return usage_window_resolver._fetch_usage_payload(access_token)
    except WeeklyUtilizationProbeError:
        raise
    except (
        urllib.error.URLError,
        http.client.HTTPException,
        TimeoutError,
        OSError,
        ValueError,
    ) as probe_error:
        raise WeeklyUtilizationProbeError(
            USAGE_PROBE_FAILED_ERROR_TEMPLATE.format(error=probe_error)
        ) from probe_error


def probe_account_meters(credentials_path: Path) -> AccountUsageMeters:
    """Read short and weekly usage meters for one account."""
    usage_window_resolver = _load_resolve_usage_window_module()
    usage_payload = _fetch_account_usage_payload(usage_window_resolver, credentials_path)
    usage_windows = usage_window_resolver.extract_usage_windows(usage_payload)
    return AccountUsageMeters(
        session_utilization=usage_windows.session_utilization,
        session_resets_at=usage_windows.session_resets_at,
        weekly_utilization=usage_windows.weekly_utilization,
        weekly_resets_at=usage_windows.weekly_resets_at,
    )
