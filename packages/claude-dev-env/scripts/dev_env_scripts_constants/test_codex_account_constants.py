"""The Codex account constants match what docs/codex-accounts.md tells the reader."""

from __future__ import annotations

from pathlib import Path

from dev_env_scripts_constants import codex_account_constants as constants

CODEX_ACCOUNTS_DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "codex-accounts.md"


def documented_text() -> str:
    return " ".join(CODEX_ACCOUNTS_DOC_PATH.read_text(encoding="utf-8").split())


def documented_list(all_names: list[str]) -> str:
    all_quoted_names = [f"`{each_name}`" for each_name in all_names]
    return ", ".join(all_quoted_names[:-1]) + f" and {all_quoted_names[-1]}"


def test_fallback_roster_matches_the_documented_accounts() -> None:
    expected_sentence = (
        "When neither exists, the accounts are "
        + documented_list(list(constants.ALL_CODEX_ACCOUNT_NAMES))
        + "."
    )
    assert expected_sentence in documented_text()


def test_shared_home_entries_match_the_documented_list() -> None:
    expected_sentence = "They are " + documented_list(sorted(constants.ALL_SHARED_CODEX_HOME_NAMES)) + "."
    assert expected_sentence in documented_text()


def test_sign_in_file_stays_per_account() -> None:
    assert constants.CODEX_AUTH_FILE_NAME not in constants.ALL_SHARED_CODEX_HOME_NAMES


def test_launcher_matches_the_documented_name_and_variable() -> None:
    launcher_file_name = constants.CODEX_LAUNCHER_PROGRAM.file_name_template.format(profile_name="<name>")
    expected_sentence = (
        f"Each roster account gets a launcher, `{launcher_file_name}`, in `~/.local/bin`. "
        f"It sets `{constants.CODEX_LAUNCHER_PROGRAM.environment_variable}` to that account's home "
        f"and runs Codex with every argument"
    )
    assert expected_sentence in documented_text()


def test_tier_bars_match_the_documented_table() -> None:
    normal_bar = f"{constants.NORMAL_TIER_MINIMUM_PERCENT_LEFT:.0f}%"
    luna_stop = f"{constants.LUNA_TIER_STOP_PERCENT_LEFT:.0f}%"
    luna_short_window_floor = f"{constants.LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT:.0f}%"
    all_expected_rows = [
        f"| One or more accounts with more than {normal_bar} left | `{constants.TIER_NORMAL}` on the account with the most room |",
        f"| No account over {normal_bar}, one or more over {luna_stop} | `{constants.TIER_LUNA}` on the account with the most room |",
        f"| An account that reports a 5-hour window, with under {luna_short_window_floor} of that window left | never takes `{constants.TIER_LUNA}` |",
        f"| No account over {luna_stop} | `{constants.TIER_WAIT}`, naming the next reset when known |",
    ]
    doc_text = documented_text()
    for each_row in all_expected_rows:
        assert each_row in doc_text


def test_documented_picker_output_carries_the_normal_tier() -> None:
    assert f'"tier": "{constants.TIER_NORMAL}"' in documented_text()
