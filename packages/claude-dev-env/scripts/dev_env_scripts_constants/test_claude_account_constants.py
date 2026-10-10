"""The picker report and meter keys stay distinct."""

from __future__ import annotations

from dev_env_scripts_constants.claude_account_constants import (
    ALL_ACCOUNT_LOCAL_NAME_PREFIXES,
    ALL_ACCOUNT_LOCAL_NAMES,
    CREDENTIALS_FILE_NAME,
    JSON_ACCOUNT_KEY,
    JSON_CONFIG_DIRECTORY_KEY,
    JSON_LAUNCHER_KEY,
    JSON_LINKED_KEY,
    JSON_METERS_KEY,
    JSON_MOVED_ASIDE_KEY,
    JSON_REASON_KEY,
    JSON_SESSION_RESETS_AT_KEY,
    JSON_SESSION_USED_PERCENT_KEY,
    JSON_UNLINKED_KEY,
    JSON_WEEKLY_RESETS_AT_KEY,
    JSON_WEEKLY_USED_PERCENT_KEY,
)


def test_picker_report_keys_never_collide() -> None:
    all_report_keys = [
        JSON_ACCOUNT_KEY,
        JSON_CONFIG_DIRECTORY_KEY,
        JSON_REASON_KEY,
        JSON_METERS_KEY,
    ]
    all_meter_keys = [
        JSON_SESSION_USED_PERCENT_KEY,
        JSON_SESSION_RESETS_AT_KEY,
        JSON_WEEKLY_USED_PERCENT_KEY,
        JSON_WEEKLY_RESETS_AT_KEY,
    ]
    assert len(set(all_report_keys)) == len(all_report_keys)
    assert len(set(all_meter_keys)) == len(all_meter_keys)


def test_sign_in_file_stays_with_its_own_account() -> None:
    assert CREDENTIALS_FILE_NAME in ALL_ACCOUNT_LOCAL_NAMES
    assert CREDENTIALS_FILE_NAME.startswith(ALL_ACCOUNT_LOCAL_NAME_PREFIXES)


def test_sync_report_keys_never_collide() -> None:
    all_sync_keys = [
        JSON_LINKED_KEY,
        JSON_MOVED_ASIDE_KEY,
        JSON_UNLINKED_KEY,
        JSON_LAUNCHER_KEY,
    ]
    assert len(set(all_sync_keys)) == len(all_sync_keys)
