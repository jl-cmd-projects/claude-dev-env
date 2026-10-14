"""The Codex account constants match what docs/codex-accounts.md tells the reader."""

from __future__ import annotations

from pathlib import Path

from dev_env_scripts_constants import codex_account_constants as constants
from dev_env_scripts_constants.claude_account_constants import ALL_LAUNCHER_DIRECTORY_RELATIVE_PARTS

CODEX_ACCOUNTS_DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "codex-accounts.md"
SECTION_HEADING_PREFIX = "## "


def documented_section(heading: str) -> str:
    all_doc_lines = CODEX_ACCOUNTS_DOC_PATH.read_text(encoding="utf-8").splitlines()
    heading_index = all_doc_lines.index(SECTION_HEADING_PREFIX + heading)
    all_section_lines: list[str] = []
    for each_line in all_doc_lines[heading_index + 1 :]:
        if each_line.startswith(SECTION_HEADING_PREFIX):
            break
        all_section_lines.append(each_line)
    return " ".join(" ".join(all_section_lines).split())


def documented_list(all_names: list[str]) -> str:
    *all_leading_names, last_name = [f"`{each_name}`" for each_name in all_names]
    if not all_leading_names:
        return last_name
    return ", ".join(all_leading_names) + f" and {last_name}"


def documented_percent(percent: float) -> str:
    return f"{percent:g}%"


def test_fallback_roster_matches_the_documented_accounts() -> None:
    expected_sentence = (
        "When neither exists, the accounts are "
        + documented_list(list(constants.ALL_CODEX_ACCOUNT_NAMES))
        + "."
    )
    assert expected_sentence in documented_section("Names and order")


def test_shared_home_entries_match_the_documented_list() -> None:
    expected_sentence = "They are " + documented_list(sorted(constants.ALL_SHARED_CODEX_HOME_NAMES)) + "."
    assert expected_sentence in documented_section("Sign in once")


def test_sign_in_file_stays_per_account() -> None:
    assert constants.CODEX_AUTH_FILE_NAME not in constants.ALL_SHARED_CODEX_HOME_NAMES


def test_launcher_matches_the_documented_name_directory_and_variable() -> None:
    launcher_file_name = constants.CODEX_LAUNCHER_PROGRAM.file_name_template.format(profile_name="<name>")
    launcher_directory = "/".join(["~", *ALL_LAUNCHER_DIRECTORY_RELATIVE_PARTS])
    expected_sentence = (
        f"Each roster account gets a launcher, `{launcher_file_name}`, in `{launcher_directory}`. "
        f"It sets `{constants.CODEX_LAUNCHER_PROGRAM.environment_variable}` to that account's home "
        f"and runs Codex with every argument"
    )
    assert expected_sentence in documented_section("Named launchers")


def test_tier_bars_match_the_documented_table() -> None:
    normal_bar = documented_percent(constants.NORMAL_TIER_MINIMUM_PERCENT_LEFT)
    luna_stop = documented_percent(constants.LUNA_TIER_STOP_PERCENT_LEFT)
    luna_short_window_floor = documented_percent(constants.LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT)
    all_expected_rows = [
        f"| One or more accounts with more than {normal_bar} left | `{constants.TIER_NORMAL}` on the account with the most room |",
        f"| No account over {normal_bar}, one or more over {luna_stop} | `{constants.TIER_LUNA}` on the account with the most room |",
        f"| An account that reports a window shorter than a week, such as the 5-hour window, with under {luna_short_window_floor} of that window left | never takes `{constants.TIER_LUNA}` |",
        f"| No account over {luna_stop} | `{constants.TIER_WAIT}`, naming the next reset when known |",
    ]
    section_text = documented_section("Which account a job uses")
    for each_row in all_expected_rows:
        assert each_row in section_text


def test_documented_choose_sample_names_the_normal_tier() -> None:
    assert f'"tier": "{constants.TIER_NORMAL}"' in documented_section("Which account a job uses")
