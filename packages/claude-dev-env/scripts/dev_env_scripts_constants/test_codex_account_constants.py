"""The documented Codex account defaults and launcher stay stable."""

from __future__ import annotations

from dev_env_scripts_constants import codex_account_constants as constants


def test_fallback_account_roster() -> None:
    assert constants.ALL_CODEX_ACCOUNT_NAMES == (
        "codex-1",
        "codex-2",
        "codex-3",
        "codex-4",
    )


def test_named_launcher_uses_the_account_home() -> None:
    assert constants.CODEX_LAUNCHER_PROGRAM.program == "codex"
    assert constants.CODEX_LAUNCHER_PROGRAM.environment_variable == "CODEX_HOME"
    assert constants.CODEX_LAUNCHER_PROGRAM.file_name_template == "codex-{profile_name}.cmd"


def test_account_tier_limits() -> None:
    assert constants.NORMAL_TIER_MINIMUM_PERCENT_LEFT == 10.0
    assert constants.LUNA_TIER_STOP_PERCENT_LEFT == 1.0
    assert constants.LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT == 20.0
