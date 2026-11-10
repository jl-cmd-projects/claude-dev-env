"""Behavioral tests for choosing the Codex account a review runs on."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import codex_review_account as account
from codex_review_scripts_constants.account_constants import (
    ACCOUNT_BROKER_CHOOSE_COMMAND,
    ACCOUNT_BROKER_CODEX_PRODUCT,
    ACCOUNT_BROKER_HOME_FLAG,
    ACCOUNT_BROKER_PRODUCT_FLAG,
    ALL_ACCOUNT_BROKER_REQUIRE_TIER_ARGUMENTS,
    ALL_RUN_TIERS,
    BROKER_WAIT_EXIT_CODE,
    NO_ACCOUNT_EXIT_CODE,
)

CODEX_HOME_VARIABLE = "CODEX_HOME"
ACCOUNT_ENVIRONMENT_VARIABLES = (
    "CODEX_ACCOUNT_PROFILES",
    "CODEX_PROFILES_ROOT",
    "CODEX_WEEKLY_FLOOR_DISABLED",
    "CLAUDE_ACCOUNT_PROFILES",
    "CLAUDE_PROFILES_ROOT",
)
NORMAL_ANSWER_REASON = "codex-1 has 62% left"
WAIT_ANSWER_REASON = "no account has room; next reset at 2026-11-10T00:00:00Z"
NORMAL_ANSWER_REASON_FOR_DEFAULT_HOME = "default has 62% left"
FAKE_CODEX_PLAN_VARIABLE = "FAKE_CODEX_PLAN"
FAKE_CODEX_CREDITS_VARIABLE = "FAKE_CODEX_CREDITS"
FAKE_CODEX_SCRIPT_NAME = "fake_codex.py"
WEEKLY_FLOOR_DISABLED_VARIABLE = "CODEX_WEEKLY_FLOOR_DISABLED"
WINDOWS_LAUNCHER_TEMPLATE = '@"{python}" "{script}" %*'
POSIX_LAUNCHER_TEMPLATE = '#!/bin/sh\nexec "{python}" "{script}" "$@"'
FAKE_CODEX_SOURCE = """import json, os, sys
for each_line in sys.stdin:
    if json.loads(each_line).get("id") == 2:
        window = {"usedPercent": 38, "windowDurationMins": 300}
        limits = {"planType": os.environ["FAKE_CODEX_PLAN"], "primary": window, "secondary": window}
        if os.environ.get("FAKE_CODEX_CREDITS"):
            limits["credits"] = {"hasCredits": True, "unlimited": True, "balance": "12.5"}
        print(json.dumps({"id": 2, "result": {"rateLimits": limits}}), flush=True)
"""


def _answer_text(tier: str, action: str, home: object, reason: object) -> str:
    return json.dumps(
        {
            "decision": {
                "action": action,
                "account": "codex-1",
                "profile": "codex-1",
                "home": home,
                "reason": reason,
                "tier": tier,
                "resets_at": None,
            },
            "accounts": [],
            "state_path": "state.json",
        }
    )


def test_normal_tier_answer_names_the_home_the_review_runs_on(tmp_path: Path) -> None:
    chosen_home = account.codex_home_from_broker_answer(
        0,
        _answer_text("normal", "run", str(tmp_path / "codex-1"), NORMAL_ANSWER_REASON),
    )

    assert chosen_home == tmp_path / "codex-1"


def test_wait_answer_refuses_the_review_and_names_the_broker_reason() -> None:
    with pytest.raises(account.CodexAccountUnavailable) as refusal:
        account.codex_home_from_broker_answer(
            BROKER_WAIT_EXIT_CODE,
            _answer_text("wait", "wait", None, WAIT_ANSWER_REASON),
        )

    assert refusal.value.exit_code == NO_ACCOUNT_EXIT_CODE
    assert WAIT_ANSWER_REASON in refusal.value.reason


def test_luna_tier_answer_refuses_the_review(tmp_path: Path) -> None:
    with pytest.raises(account.CodexAccountUnavailable) as refusal:
        account.codex_home_from_broker_answer(
            0,
            _answer_text(
                "luna", "run", str(tmp_path / "codex-1"), "codex-1 has 4% left"
            ),
        )

    assert refusal.value.exit_code == NO_ACCOUNT_EXIT_CODE
    assert "codex-1 has 4% left" in refusal.value.reason


def test_broker_failure_exit_is_reported_with_its_own_exit_code() -> None:
    with pytest.raises(account.CodexAccountUnavailable) as refusal:
        account.codex_home_from_broker_answer(2, "cannot read account list")

    assert refusal.value.exit_code == 2
    assert "2" in refusal.value.reason


@pytest.mark.parametrize(
    "answer_text",
    [
        "",
        "not json",
        "[]",
        "{}",
        '{"decision": "run"}',
        json.dumps({"decision": {"tier": "normal"}}),
        _answer_text("normal", "run", "", NORMAL_ANSWER_REASON),
        _answer_text("normal", "run", None, NORMAL_ANSWER_REASON),
        _answer_text("normal", "run", 7, NORMAL_ANSWER_REASON),
    ],
)
def test_unusable_answer_refuses_the_review(answer_text: str) -> None:
    with pytest.raises(account.CodexAccountUnavailable) as refusal:
        account.codex_home_from_broker_answer(0, answer_text)

    assert refusal.value.exit_code == NO_ACCOUNT_EXIT_CODE


def test_wait_answer_without_a_reason_still_refuses() -> None:
    with pytest.raises(account.CodexAccountUnavailable):
        account.codex_home_from_broker_answer(
            BROKER_WAIT_EXIT_CODE, _answer_text("wait", "wait", None, None)
        )


def test_broker_path_names_the_script_beside_the_shared_tree() -> None:
    assert account.account_broker_path().is_file()
    assert account.account_broker_path().name == "account_broker.py"
    assert account.account_broker_path().parent.name == "scripts"


def test_broker_command_asks_for_the_codex_choice() -> None:
    assert account.broker_choose_command() == [
        sys.executable,
        str(account.account_broker_path()),
        ACCOUNT_BROKER_CHOOSE_COMMAND,
        ACCOUNT_BROKER_PRODUCT_FLAG,
        ACCOUNT_BROKER_CODEX_PRODUCT,
        *ALL_ACCOUNT_BROKER_REQUIRE_TIER_ARGUMENTS,
    ]


def test_home_check_command_names_the_home_and_requires_no_tier(tmp_path: Path) -> None:
    assert account.broker_home_check_command(str(tmp_path)) == [
        sys.executable,
        str(account.account_broker_path()),
        ACCOUNT_BROKER_CHOOSE_COMMAND,
        ACCOUNT_BROKER_PRODUCT_FLAG,
        ACCOUNT_BROKER_CODEX_PRODUCT,
        ACCOUNT_BROKER_HOME_FLAG,
        str(tmp_path),
    ]


def test_luna_answer_is_accepted_when_the_caller_allows_every_run_tier(
    tmp_path: Path,
) -> None:
    chosen_home = account.codex_home_from_broker_answer(
        0,
        _answer_text("luna", "run", str(tmp_path / "codex-1"), "codex-1 has 4% left"),
        ALL_RUN_TIERS,
    )

    assert chosen_home == tmp_path / "codex-1"


def test_wait_answer_is_refused_even_when_the_caller_allows_every_run_tier() -> None:
    with pytest.raises(account.CodexAccountUnavailable):
        account.codex_home_from_broker_answer(
            BROKER_WAIT_EXIT_CODE,
            _answer_text("wait", "wait", None, WAIT_ANSWER_REASON),
            ALL_RUN_TIERS,
        )


def _install_fake_codex(directory: Path) -> None:
    script = directory / FAKE_CODEX_SCRIPT_NAME
    script.write_text(FAKE_CODEX_SOURCE, encoding="utf-8")
    if os.name == "nt":
        launcher = directory / "codex.cmd"
        launcher.write_text(
            WINDOWS_LAUNCHER_TEMPLATE.format(python=sys.executable, script=script),
            encoding="utf-8",
        )
        return
    launcher = directory / "codex"
    launcher.write_text(
        POSIX_LAUNCHER_TEMPLATE.format(python=sys.executable, script=script),
        encoding="utf-8",
    )
    launcher.chmod(0o755)


def _run_broker_without_a_roster(
    tmp_path: Path,
    fake_plan: str | None,
    *,
    is_home_check: bool = False,
    extra_environment: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    default_home = tmp_path / "default-codex-home"
    default_home.mkdir()
    codex_directory = tmp_path / "codex-bin"
    codex_directory.mkdir()
    if fake_plan is not None:
        _install_fake_codex(codex_directory)
    broker_environment = {
        each_name: each_setting
        for each_name, each_setting in os.environ.items()
        if each_name not in ACCOUNT_ENVIRONMENT_VARIABLES
    }
    broker_environment.update(
        {
            "HOME": str(isolated_home),
            "USERPROFILE": str(isolated_home),
            "PATH": str(codex_directory),
            CODEX_HOME_VARIABLE: str(default_home),
            FAKE_CODEX_PLAN_VARIABLE: fake_plan or "",
            **(extra_environment or {}),
        }
    )
    broker_command = (
        account.broker_home_check_command(str(default_home))
        if is_home_check
        else account.broker_choose_command()
    )
    completed = subprocess.run(
        broker_command,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=broker_environment,
    )
    return completed, default_home


def test_broker_answer_with_no_roster_reads_the_default_home_and_accepts_a_paid_plan(
    tmp_path: Path,
) -> None:
    completed, default_home = _run_broker_without_a_roster(tmp_path, "team")

    chosen_home = account.codex_home_from_broker_answer(
        completed.returncode, completed.stdout
    )
    answer = json.loads(completed.stdout)
    assert chosen_home == default_home.resolve()
    assert answer["decision"]["tier"] == "normal"
    assert answer["decision"]["reason"] == NORMAL_ANSWER_REASON_FOR_DEFAULT_HOME


def test_broker_answer_with_no_roster_refuses_a_free_default_home(
    tmp_path: Path,
) -> None:
    completed, _ = _run_broker_without_a_roster(tmp_path, "free")

    with pytest.raises(account.CodexAccountUnavailable) as refusal:
        account.codex_home_from_broker_answer(completed.returncode, completed.stdout)

    assert completed.returncode == BROKER_WAIT_EXIT_CODE
    assert refusal.value.exit_code == NO_ACCOUNT_EXIT_CODE
    assert "free" in refusal.value.reason


@pytest.mark.parametrize("fake_plan", ("free_works", "free trial"))
def test_broker_answer_with_no_roster_refuses_a_default_home_on_an_unrecognised_plan(
    tmp_path: Path, fake_plan: str
) -> None:
    completed, _ = _run_broker_without_a_roster(tmp_path, fake_plan)

    with pytest.raises(account.CodexAccountUnavailable) as refusal:
        account.codex_home_from_broker_answer(completed.returncode, completed.stdout)

    assert completed.returncode == BROKER_WAIT_EXIT_CODE
    assert refusal.value.exit_code == NO_ACCOUNT_EXIT_CODE
    assert "reports no known plan and is never chosen" in refusal.value.reason


def test_exported_home_check_refuses_a_home_on_an_unrecognised_plan(tmp_path: Path) -> None:
    completed, _ = _run_broker_without_a_roster(tmp_path, "free_works", is_home_check=True)

    with pytest.raises(account.CodexAccountUnavailable) as refusal:
        account.codex_home_from_broker_answer(
            completed.returncode, completed.stdout, ALL_RUN_TIERS
        )

    assert completed.returncode == BROKER_WAIT_EXIT_CODE
    assert refusal.value.exit_code == NO_ACCOUNT_EXIT_CODE
    assert "reports no known plan and is never chosen" in refusal.value.reason


def test_exported_home_check_does_not_let_credits_or_the_floor_switch_unlock_an_unrecognised_plan(
    tmp_path: Path,
) -> None:
    completed, _ = _run_broker_without_a_roster(
        tmp_path,
        "free_works",
        is_home_check=True,
        extra_environment={
            FAKE_CODEX_CREDITS_VARIABLE: "1",
            WEEKLY_FLOOR_DISABLED_VARIABLE: "1",
        },
    )

    with pytest.raises(account.CodexAccountUnavailable) as refusal:
        account.codex_home_from_broker_answer(
            completed.returncode, completed.stdout, ALL_RUN_TIERS
        )

    assert completed.returncode == BROKER_WAIT_EXIT_CODE
    assert "reports no known plan and is never chosen" in refusal.value.reason


def test_exported_home_check_accepts_a_home_on_a_paid_plan(tmp_path: Path) -> None:
    completed, default_home = _run_broker_without_a_roster(
        tmp_path, "plus", is_home_check=True
    )

    chosen_home = account.codex_home_from_broker_answer(
        completed.returncode, completed.stdout, ALL_RUN_TIERS
    )

    assert chosen_home == default_home.resolve()


def test_broker_answer_with_no_roster_refuses_when_the_default_home_cannot_be_read(
    tmp_path: Path,
) -> None:
    completed, _ = _run_broker_without_a_roster(tmp_path, None)

    with pytest.raises(account.CodexAccountUnavailable) as refusal:
        account.codex_home_from_broker_answer(completed.returncode, completed.stdout)

    assert completed.returncode == BROKER_WAIT_EXIT_CODE
    assert refusal.value.exit_code == NO_ACCOUNT_EXIT_CODE
