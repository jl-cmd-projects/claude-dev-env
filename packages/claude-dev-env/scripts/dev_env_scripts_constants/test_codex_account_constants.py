"""The Codex account constants match what docs/codex-accounts.md tells the reader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dev_env_scripts_constants import codex_account_constants as constants
from dev_env_scripts_constants.account_broker_constants import METER_READ_ATTEMPTS, meter_read_delay_seconds
from dev_env_scripts_constants.claude_account_constants import ALL_LAUNCHER_DIRECTORY_RELATIVE_PARTS

CODEX_ACCOUNTS_DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "codex-accounts.md"
SECTION_HEADING_PREFIX = "## "
CHOOSE_COMMAND_SUFFIX = "choose --product codex"
CODE_FENCE = "```"


def documented_section_lines(heading: str) -> list[str]:
    all_doc_lines = CODEX_ACCOUNTS_DOC_PATH.read_text(encoding="utf-8").splitlines()
    heading_index = all_doc_lines.index(SECTION_HEADING_PREFIX + heading)
    all_section_lines: list[str] = []
    for each_line in all_doc_lines[heading_index + 1 :]:
        if each_line.startswith(SECTION_HEADING_PREFIX):
            break
        all_section_lines.append(each_line)
    return all_section_lines


def documented_section(heading: str) -> str:
    return " ".join(" ".join(documented_section_lines(heading)).split())


def documented_choose_sample() -> dict[str, Any]:
    all_section_lines = documented_section_lines("Which account a job uses")
    command_index = next(
        index for index, each_line in enumerate(all_section_lines) if each_line.endswith(CHOOSE_COMMAND_SUFFIX)
    )
    fence_index = all_section_lines.index(CODE_FENCE, command_index)
    return json.loads("\n".join(all_section_lines[command_index + 1 : fence_index]))


def documented_list(all_names: list[str]) -> str:
    *all_leading_names, last_name = [f"`{each_name}`" for each_name in all_names]
    if not all_leading_names:
        return last_name
    return ", ".join(all_leading_names) + f" and {last_name}"


def documented_percent(percent: float) -> str:
    return f"{percent:g}%"


def test_fallback_roster_matches_the_documented_accounts() -> None:
    expected_sentence = (
        "When neither exists, the roster is empty. "
        "The broker's `choose` and `check` then read the default Codex home "
        f"as the account `{constants.NO_ROSTER_ACCOUNT_NAME}`, and `install` has no accounts. "
        "`sync` falls back to "
        + documented_list(list(constants.ALL_CODEX_ACCOUNT_NAMES))
        + " when no list names an account. "
        f"`choose` and `check` fall back to them only when `{constants.CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE}` "
        f"holds only separators, such as `{constants.CODEX_ACCOUNT_NAME_SEPARATOR}`, and no saved list names an account."
    )
    assert expected_sentence in documented_section("Names and order")


def test_shared_home_entries_match_the_documented_list() -> None:
    expected_sentence = "They are " + documented_list(sorted(constants.ALL_SHARED_CODEX_HOME_NAMES)) + "."
    assert expected_sentence in documented_section("Sign in once")


def test_sign_in_file_stays_per_account() -> None:
    expected_sentence = f"The sign-in lives in that folder's `{constants.CODEX_AUTH_FILE_NAME}`."
    assert expected_sentence in documented_section("Sign in once")
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
    pro_plans = documented_list(sorted(constants.ALL_PRO_PLAN_TYPES))
    other_paid_account = "an account on another paid plan"
    no_pro_account = f"No Pro plan account reaches `{constants.TIER_NORMAL}` or `{constants.TIER_LUNA}`"
    most_room_pro_account = "on the Pro account with the most room, before any account on another plan"
    free_plans = documented_list(sorted(constants.ALL_FREE_PLAN_TYPES))
    paid_plans = documented_list(sorted(constants.ALL_PAID_PLAN_TYPES))
    pro_stop = documented_percent(constants.PRO_PLAN_STOP_PERCENT_LEFT)
    credits_condition = (
        f"`{constants.HAS_CREDITS_KEY}` is `true` with a balance above zero, "
        f"or `{constants.UNLIMITED_CREDITS_KEY}` is `true`"
    )
    other_paid_luna_condition = (
        f"with more than {luna_stop} of its week left and at least {luna_short_window_floor} left "
        "in any window shorter than a week"
    )
    credits_answer = (
        f"`{constants.TIER_NORMAL}`, even at or under {luna_stop} of its week left or under {luna_short_window_floor} "
        f"of a short window; the rows above that give `{constants.TIER_LUNA}` count only accounts without credits; "
        "a Pro plan account with credits comes before every account on another plan; "
        "among accounts of the same kind, the one with the most room, so plan usage comes before credits alone"
    )
    same_group_condition = (
        "Within one plan group (the Pro plan accounts, or the accounts on another paid plan), "
        f"one account reaches `{constants.TIER_NORMAL}` and another reaches only `{constants.TIER_LUNA}`"
    )
    all_expected_rows = [
        f"| A Pro plan account ({pro_plans}) with more than {normal_bar} left | `{constants.TIER_NORMAL}` {most_room_pro_account} |",
        (
            f"| No such Pro account, and a Pro plan account with more than {pro_stop} left in each window | `{constants.TIER_LUNA}` "
            f"{most_room_pro_account}, even one with more than {normal_bar} left |"
        ),
        f"| {no_pro_account}, and {other_paid_account} with more than {normal_bar} left | `{constants.TIER_NORMAL}` on the account with the most room |",
        (
            f"| {no_pro_account}, no other account over {normal_bar}, and {other_paid_account} "
            f"{other_paid_luna_condition} | `{constants.TIER_LUNA}` on the account with the most room |"
        ),
        f"| {same_group_condition} | the `{constants.TIER_NORMAL}` account, whatever the room of each |",
        f"| An account on a free plan ({free_plans}) | never chosen, whatever its room or credits; a `{constants.TIER_WAIT}` reason names it |",
        f"| An account whose plan is missing, blank or not one of the paid plans, which are {paid_plans} | never chosen, whatever its room or credits; a `{constants.TIER_WAIT}` reason names it |",
        (
            f"| An account with credits ({credits_condition}) and {normal_bar} or less left "
            f"| {credits_answer} |"
        ),
        f"| An account on another paid plan that reports a window shorter than a week, such as the 5-hour window, with under {luna_short_window_floor} of that window left | never takes `{constants.TIER_LUNA}` |",
        (
            f"| No account can run: no Pro plan account with more than {pro_stop} left in each window, "
            f"no account on another paid plan with over {normal_bar} left or {other_paid_luna_condition}, "
            f"and no account with credits | `{constants.TIER_WAIT}`, naming the next reset when known |"
        ),
    ]
    section_text = documented_section("Which account a job uses")
    for each_row in all_expected_rows:
        assert each_row in section_text


def test_tier_requirement_matches_the_documented_paragraph() -> None:
    required_tier = f"`{constants.REQUIRE_TIER_ARGUMENT} {constants.TIER_NORMAL}`"
    all_expected_sentences = [
        f"A caller that needs the `{constants.TIER_NORMAL}` tier passes {required_tier}.",
        (
            f"The broker then chooses a Pro plan account only when it reaches `{constants.TIER_NORMAL}`, "
            "and otherwise the account on another paid plan with the most room that does."
        ),
        (
            f"A caller that passes no tier takes a Pro plan account first, even on `{constants.TIER_LUNA}`, "
            "before an account on another plan with more room."
        ),
    ]
    section_text = documented_section("Which account a job uses")
    for each_sentence in all_expected_sentences:
        assert each_sentence in section_text


def test_default_home_rule_matches_the_documented_paragraph() -> None:
    default_home = f"`{constants.CODEX_HOME_ENVIRONMENT_VARIABLE}` or `~/{constants.MAIN_CODEX_HOME_DIRECTORY_NAME}`"
    floor_switch = f"`{constants.CODEX_WEEKLY_FLOOR_DISABLED_ENVIRONMENT_VARIABLE}`"
    all_expected_sentences = [
        (
            f"With no roster configured, `choose` and `check` read the default Codex home, {default_home}, "
            f"as the account `{constants.NO_ROSTER_ACCOUNT_NAME}` and apply the same rules."
        ),
        f"A `{constants.CODEX_HOME_ENVIRONMENT_VARIABLE}` that is empty or only whitespace counts as unset.",
        f"A failed read gives `{constants.TIER_WAIT}` and exit 3, and the reason names the failure.",
        (
            "`--home <path>` judges that Codex home alone. A home on a paid plan with readable meters runs, "
            f"whatever its room, with or without credits, and whatever {floor_switch} says."
        ),
        f"It reports the tier its meters allow, or `{constants.ALL_TIERS_BEST_FIRST[-1]}` when no tier allows it.",
        (
            "A free, missing, blank, unknown or unlisted plan, or a home whose meters are unread, "
            f"still gives `{constants.TIER_WAIT}`."
        ),
        (
            f"`{constants.REQUIRE_TIER_ARGUMENT} {constants.TIER_NORMAL}` still applies, "
            f"so a home that does not reach `{constants.TIER_NORMAL}` gives `{constants.TIER_WAIT}`."
        ),
        "`check --home` answers as `choose --home` does.",
        (
            "A spent mark saved for the roster account that has this home, by `run` or by `choose --spent`, "
            f"still gives `{constants.TIER_WAIT}` until its reset, unless that account has spendable credits."
        ),
        (
            "A mark is keyed by product, account name and home, and `--home` reads a home the roster does not list "
            "as an account named for its folder. "
            f"So a mark saved for the no-roster default account, named `{constants.NO_ROSTER_ACCOUNT_NAME}`, "
            "does not hold `--home <that home>` unless the folder of that home is also named "
            f"`{constants.NO_ROSTER_ACCOUNT_NAME}`, and a mark saved for an account outside the roster never holds a `--home` answer."
        ),
        (
            "After an account leaves the roster, a mark saved while it was in the roster still holds "
            "`--home <its home>` only when the account's name equals the name of its resolved home folder. "
            "A roster account `Alpha` whose home folder is `alpha`, or whose home folder is a junction "
            "to a folder with another name, stops holding `--home <its home>` once it leaves the roster."
        ),
        "The broker refuses `--home` for the Claude product and with `--spent`.",
    ]
    section_text = documented_section("Which account a job uses")
    for each_sentence in all_expected_sentences:
        assert each_sentence in section_text


def test_shared_callers_match_the_documented_answers() -> None:
    all_expected_sentences = [
        (
            "Runs each live `codex exec` with `CODEX_HOME` set to `decision.home`. "
            f"With `CODEX_HOME` unset or blank, it accepts only `{constants.TIER_NORMAL}`. "
            "With a non-blank `CODEX_HOME`, it asks the broker to judge that home "
            f"and accepts `{constants.TIER_NORMAL}` or `{constants.TIER_LUNA}`, "
            "and the run uses `decision.home`, the trimmed absolute folder the broker judged. "
            f"`{constants.TIER_WAIT}`, a tier it does not accept, or a failed broker records `infra_error` "
            "with the failure `no_codex_account` and starts no model call"
        ),
        (
            f"A `{constants.TIER_WAIT}` answer or a tier it does not accept returns a `declined` fallback "
            "with the broker's reason and starts no Codex process."
        ),
        (
            "A broker that times out, cannot start, exits with a code other than 0 or 3, prints malformed JSON, "
            f"or answers `{constants.TIER_NORMAL}` or `{constants.TIER_LUNA}` with no home or no meters "
            "returns a `broken` fallback and starts no Codex process"
        ),
    ]
    section_text = documented_section("Shared callers")
    for each_sentence in all_expected_sentences:
        assert each_sentence in section_text


def test_free_plan_types_stay_apart_from_paid_plan_types() -> None:
    assert constants.ALL_FREE_PLAN_TYPES
    assert constants.ALL_FREE_PLAN_TYPES.isdisjoint(constants.ALL_PAID_PLAN_TYPES)
    assert constants.ALL_FREE_PLAN_TYPES.isdisjoint(constants.ALL_PRO_PLAN_TYPES)


def test_paid_plan_types_hold_every_pro_plan_and_the_other_paid_plans() -> None:
    all_other_paid_plans = {"team", "plus", "business", "enterprise", "edu"}

    assert constants.ALL_PRO_PLAN_TYPES <= constants.ALL_PAID_PLAN_TYPES
    assert constants.ALL_PAID_PLAN_TYPES == constants.ALL_PRO_PLAN_TYPES | all_other_paid_plans


def test_paid_plan_types_are_written_as_the_broker_compares_them() -> None:
    assert all(each_plan == each_plan.strip().casefold() and each_plan for each_plan in constants.ALL_PAID_PLAN_TYPES)


def test_weekly_floor_switch_matches_the_documented_paragraph() -> None:
    switch_name = constants.CODEX_WEEKLY_FLOOR_DISABLED_ENVIRONMENT_VARIABLE
    truthy_values = documented_list(sorted(constants.ALL_CODEX_WEEKLY_FLOOR_DISABLED_TRUTHY_VALUES))
    luna_stop = documented_percent(constants.LUNA_TIER_STOP_PERCENT_LEFT)
    luna_short_window_floor = documented_percent(constants.LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT)
    pro_stop = documented_percent(constants.PRO_PLAN_STOP_PERCENT_LEFT)
    all_expected_sentences = [
        (
            f"Set `{switch_name}` to lift the {luna_stop} weekly stop for an account on a paid plan other than a Pro plan. "
            f"The values that turn it on are {truthy_values}."
        ),
        (
            f"While it is on, such an account without credits that has {luna_stop} or less of its week left "
            f"can take `{constants.TIER_LUNA}`, and `choose` and `check` do not wait for its weekly reset."
        ),
        f"The {luna_short_window_floor} short-window floor still applies to it.",
        (
            "The switch changes nothing for a Pro plan account. "
            f"Without credits, a Pro plan account takes `{constants.TIER_LUNA}` with more than {pro_stop} left "
            f"in each window and waits at {pro_stop} in either window, whether the switch is on or off."
        ),
        (
            "An account with credits already runs under both floors, "
            "so the switch matters only for an account on another paid plan without credits."
        ),
    ]
    section_text = documented_section("Which account a job uses")
    for each_sentence in all_expected_sentences:
        assert each_sentence in section_text


def test_meter_retries_match_the_documented_table() -> None:
    all_delays = [meter_read_delay_seconds(each_attempt) for each_attempt in range(1, METER_READ_ATTEMPTS)]
    all_delay_texts = [f"{each_delay:g} second" + ("" if each_delay == 1 else "s") for each_delay in all_delays]
    all_expected_rows = [
        (
            "| A meter read finds no Codex executable, or fails with text that holds `HTTP Error 429` "
            "| The broker makes that 1 read and does not retry. "
            "A 429 text sets no rate-limit cooldown for a Codex account |"
        ),
        (
            "| A meter read fails with a `CodexMeterUnreadError`, `OSError`, `ValueError`, `RuntimeError` "
            "or `subprocess.SubprocessError` that the row above does not cover "
            f"| The broker reads it again, up to {METER_READ_ATTEMPTS} reads, "
            f"waiting {' and then '.join(all_delay_texts)} |"
        ),
        (
            "| A meter read raises any other exception type "
            "| The broker does not catch it, so the command ends with that exception after 1 read |"
        ),
    ]
    section_text = documented_section("Which account a job uses")
    for each_row in all_expected_rows:
        assert each_row in section_text


def test_documented_choose_sample_runs_normal_on_the_tightest_window() -> None:
    sample = documented_choose_sample()
    decision = sample["decision"]
    chosen_meters = next(
        each_account["meters"] for each_account in sample["accounts"] if each_account["name"] == decision["account"]
    )
    room = min(chosen_meters["session_percent_left"], chosen_meters["weekly_percent_left"])
    assert decision["tier"] == constants.TIER_NORMAL
    assert room > constants.NORMAL_TIER_MINIMUM_PERCENT_LEFT
    assert decision["reason"] == f"{decision['account']} has {room:g}% left"
