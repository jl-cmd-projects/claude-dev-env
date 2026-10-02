"""Tests for the picker that names which Codex account a runner job uses."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import codex_account_choice as choice
from claude_account_profile import links_to, write_launcher
from codex_account_meters import CodexAccountMeters, CodexMeterUnreadError, UsageWindow
from dev_env_scripts_constants.codex_account_constants import (
    CODEX_LAUNCHER_FILE_NAME_TEMPLATE,
    CODEX_LAUNCHER_TEXT_TEMPLATE,
)

NOW = datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc)
ALL_SHARED_ENTRY_NAMES = (
    "AGENTS.md",
    "agents",
    "config.toml",
    "hooks",
    "hooks.json",
    "plugins",
    "rules",
    "skills",
)
NPM_CODEX_SHIM_TEXT = (
    "@ECHO off\r\n"
    "GOTO start\r\n"
    ":find_dp0\r\n"
    "SET dp0=%~dp0\r\n"
    "EXIT /b\r\n"
    ":start\r\n"
    "SETLOCAL\r\n"
    "CALL :find_dp0\r\n"
    'SET "_prog=cmd"\r\n'
    "endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% &"
    ' "%_prog%" /d /c "echo %%CODEX_HOME%%"\r\n'
)


@pytest.fixture(autouse=True)
def clear_account_roster_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEX_ACCOUNT_PROFILES", raising=False)


def build_codex_main_home(tmp_path: Path) -> Path:
    main_home = tmp_path / "main"
    for each_directory in ("agents", "hooks", "plugins", "rules", "skills", "sessions"):
        (main_home / each_directory).mkdir(parents=True)
    for each_file in ("AGENTS.md", "config.toml", "hooks.json", "auth.json", "history.jsonl"):
        (main_home / each_file).write_text(each_file, encoding="utf-8")
    return main_home


def save_roster(profiles_root: Path, document: object) -> None:
    profiles_root.mkdir(parents=True, exist_ok=True)
    (profiles_root / "account-launchers.json").write_text(
        json.dumps(document), encoding="utf-8"
    )


def typed_lines(*all_lines: str) -> Callable[[str], str]:
    remaining_lines: Iterator[str] = iter(all_lines)

    def read_line(prompt: str) -> str:
        assert prompt == "Name for this Codex account launcher (blank to finish): "
        try:
            return next(remaining_lines)
        except StopIteration as error:
            raise EOFError from error

    return read_line


def install(main_home: Path, tmp_path: Path, *all_names: str) -> dict[str, dict[str, object]]:
    return choice.install_codex_account_launchers(
        main_home=main_home,
        profiles_root=tmp_path / "profiles",
        launcher_directory=tmp_path / "bin",
        all_names=all_names,
        now=NOW,
    )


def reading(
    name: str,
    *,
    weekly_used: float,
    short_used: float = 0.0,
    weekly_resets_in: timedelta = timedelta(days=3),
) -> choice.AccountReading:
    return choice.AccountReading(
        name=name,
        codex_home=Path("/profiles") / name,
        meters=CodexAccountMeters(
            all_windows=(
                UsageWindow(300, short_used, NOW + timedelta(hours=2)),
                UsageWindow(10080, weekly_used, NOW + weekly_resets_in),
            )
        ),
    )


def unread(name: str) -> choice.AccountReading:
    return choice.AccountReading(name, Path("/profiles") / name, None, "not signed in")


class TestChooseCodexAccount:
    def should_take_the_first_account_in_order_with_room(self) -> None:
        decision = choice.choose_codex_account(
            [reading("codex-1", weekly_used=50.0), reading("codex-2", weekly_used=0.0)]
        )
        assert (decision.tier, decision.reading.name) == ("normal", "codex-1")
        assert decision.stop_below_percent is None

    def should_pass_over_an_account_at_the_ten_percent_bar(self) -> None:
        decision = choice.choose_codex_account(
            [reading("codex-1", weekly_used=90.0), reading("codex-2", weekly_used=60.0)]
        )
        assert (decision.tier, decision.reading.name) == ("normal", "codex-2")

    def should_measure_room_by_the_tightest_window(self) -> None:
        decision = choice.choose_codex_account(
            [
                reading("codex-1", weekly_used=10.0, short_used=95.0),
                reading("codex-2", weekly_used=70.0),
            ]
        )
        assert decision.reading.name == "codex-2"

    def should_skip_an_unread_account(self) -> None:
        decision = choice.choose_codex_account(
            [unread("codex-1"), reading("codex-2", weekly_used=20.0)]
        )
        assert (decision.tier, decision.reading.name) == ("normal", "codex-2")

    def should_fall_back_to_luna_on_the_roomiest_account_under_the_bar(self) -> None:
        decision = choice.choose_codex_account(
            [
                reading("codex-1", weekly_used=97.0),
                reading("codex-2", weekly_used=92.0),
                reading("codex-3", weekly_used=100.0),
            ]
        )
        assert (decision.tier, decision.reading.name) == ("luna", "codex-2")
        assert decision.stop_below_percent == 1.0

    def should_keep_luna_off_an_account_under_twenty_percent_of_its_five_hour_window(
        self,
    ) -> None:
        decision = choice.choose_codex_account(
            [
                reading("codex-1", weekly_used=92.0, short_used=85.0),
                reading("codex-2", weekly_used=97.0, short_used=80.0),
            ]
        )
        assert (decision.tier, decision.reading.name) == ("luna", "codex-2")

    def should_run_luna_on_an_account_with_no_five_hour_window(self) -> None:
        weekly_only = choice.AccountReading(
            "codex-3",
            Path("/profiles/codex-3"),
            CodexAccountMeters((UsageWindow(10080, 95.0, NOW + timedelta(days=1)),)),
        )
        decision = choice.choose_codex_account(
            [reading("codex-1", weekly_used=92.0, short_used=90.0), weekly_only]
        )
        assert (decision.tier, decision.reading.name) == ("luna", "codex-3")

    def should_wait_on_the_account_that_resets_first_when_none_passes_one_percent(
        self,
    ) -> None:
        decision = choice.choose_codex_account(
            [
                reading(
                    "codex-1", weekly_used=99.5, weekly_resets_in=timedelta(days=2)
                ),
                reading(
                    "codex-2", weekly_used=100.0, weekly_resets_in=timedelta(hours=6)
                ),
            ]
        )
        assert decision.tier == "wait"
        assert decision.reading.name == "codex-2"
        assert (NOW + timedelta(hours=6)).isoformat() in decision.reason

    def should_wait_when_no_meter_reads(self) -> None:
        decision = choice.choose_codex_account([unread("codex-1"), unread("codex-2")])
        assert (decision.tier, decision.reading) == ("wait", None)


class TestDecisionPayload:
    def should_name_no_account_or_home_on_wait(self) -> None:
        all_readings = [reading("codex-1", weekly_used=100.0)]
        payload = choice.decision_payload(
            choice.choose_codex_account(all_readings), all_readings
        )
        assert (payload["tier"], payload["account"], payload["codex_home"]) == (
            "wait",
            None,
            None,
        )

    def should_report_every_account_and_the_chosen_home(self) -> None:
        all_readings = [unread("codex-1"), reading("codex-2", weekly_used=25.0)]
        payload = choice.decision_payload(
            choice.choose_codex_account(all_readings), all_readings
        )
        assert payload["codex_home"] == str(Path("/profiles") / "codex-2")
        assert payload["percent_left"] == 75.0
        assert [each["name"] for each in payload["accounts"]] == ["codex-1", "codex-2"]
        assert payload["accounts"][0]["unread"] == "not signed in"
        json.dumps(payload)


class TestReadAccount:
    def should_call_an_account_without_a_sign_in_unread(self, tmp_path: Path) -> None:
        def never_called(codex_home: Path) -> CodexAccountMeters:
            raise AssertionError("no sign-in, no read")

        account_reading = choice.read_account("codex-1", tmp_path, never_called)
        assert (account_reading.meters, account_reading.unread_reason) == (None, "not signed in")

    def should_read_under_the_accounts_own_home(self, tmp_path: Path) -> None:
        (tmp_path / "codex-2").mkdir()
        (tmp_path / "codex-2" / "auth.json").write_text("{}")
        all_homes: list[Path] = []

        def fake_reader(codex_home: Path) -> CodexAccountMeters:
            all_homes.append(codex_home)
            return CodexAccountMeters((UsageWindow(10080, 40.0, None),))

        account_reading = choice.read_account("codex-2", tmp_path, fake_reader)
        assert all_homes == [tmp_path / "codex-2"]
        assert account_reading.meters.percent_left == 60.0

    def should_keep_the_unread_reason(self, tmp_path: Path) -> None:
        (tmp_path / "codex-1").mkdir()
        (tmp_path / "codex-1" / "auth.json").write_text("{}")

        def failing_reader(codex_home: Path) -> CodexAccountMeters:
            raise CodexMeterUnreadError("codex app-server sent no rate-limit reply")

        account_reading = choice.read_account("codex-1", tmp_path, failing_reader)
        assert account_reading.unread_reason == "codex app-server sent no rate-limit reply"


class TestCheck:
    @pytest.mark.parametrize(
        ("weekly_used", "exit_code"), [(98.0, 0), (99.0, 3), (100.0, 3)]
    )
    def should_answer_room_only_above_the_floor(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        weekly_used: float,
        exit_code: int,
    ) -> None:
        (tmp_path / "codex-3").mkdir()
        (tmp_path / "codex-3" / "auth.json").write_text("{}")
        monkeypatch.setattr(
            choice,
            "_meter_reader",
            lambda codex_path: (
                lambda codex_home: CodexAccountMeters(
                    (UsageWindow(10080, weekly_used, None),)
                )
            ),
        )
        assert (
            choice.main(["--profiles-root", str(tmp_path), "check", "codex-3"])
            == exit_code
        )

    def should_answer_no_room_for_an_unread_account(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(choice, "_meter_reader", lambda codex_path: None)
        assert choice.main(["--profiles-root", str(tmp_path), "check", "codex-4"]) == 3


class TestSync:
    @pytest.mark.skipif(
        os.name == "nt", reason="junction creation needs a Windows shell"
    )
    def should_link_the_shared_setup_and_keep_each_sign_in(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main_home = tmp_path / "main"
        (main_home / "rules").mkdir(parents=True)
        (main_home / "config.toml").write_text("model = 'x'")
        (main_home / "auth.json").write_text("{}")
        (main_home / "sessions").mkdir()
        profiles_root = tmp_path / "profiles"

        assert (
            choice.main(
                [
                    "--profiles-root",
                    str(profiles_root),
                    "sync",
                    "--main-home",
                    str(main_home),
                ]
            )
            == 0
        )

        report = json.loads(capsys.readouterr().out)
        assert list(report) == ["codex-1", "codex-2", "codex-3", "codex-4"]
        each_home = profiles_root / "codex-3"
        assert os.readlink(each_home / "rules") == str(main_home / "rules")
        assert os.readlink(each_home / "config.toml") == str(main_home / "config.toml")
        assert not (each_home / "auth.json").exists()
        assert not (each_home / "sessions").exists()


class TestSmallHelpers:
    @pytest.mark.parametrize(
        ("entry_name", "is_local"),
        [("auth.json", True), ("sessions", True), ("state_5.sqlite", True), ("config.toml", False), ("plugins", False), ("agents", False)],
    )
    def should_keep_every_entry_outside_the_shared_set_per_account(
        self, entry_name: str, is_local: bool
    ) -> None:
        assert choice.is_account_local_codex_entry(entry_name) is is_local

    def should_take_the_profiles_root_from_the_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CODEX_PROFILES_ROOT", str(tmp_path))
        assert choice.default_profiles_root() == tmp_path

    def should_default_the_profiles_root_under_the_user_home(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CODEX_PROFILES_ROOT", raising=False)
        assert choice.default_profiles_root() == Path.home() / ".codex-profiles"

    def should_list_each_window_in_a_read_accounts_payload(self) -> None:
        payload = choice.reading_payload(reading("codex-1", weekly_used=40.0, short_used=5.0))
        assert payload["percent_left"] == 60.0
        assert [each["minutes"] for each in payload["windows"]] == [300, 10080]


class TestAccountRoster:
    def should_take_the_environment_roster_over_the_saved_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        save_roster(tmp_path, ["gamma"])
        monkeypatch.setenv("CODEX_ACCOUNT_PROFILES", " beta , alpha,, ")
        assert choice.saved_codex_account_names(tmp_path) == ("beta", "alpha")

    def should_read_the_saved_file_when_the_environment_is_unset(
        self, tmp_path: Path
    ) -> None:
        save_roster(tmp_path, ["gamma", "alpha"])
        assert choice.saved_codex_account_names(tmp_path) == ("gamma", "alpha")

    def should_name_no_account_when_neither_is_set(self, tmp_path: Path) -> None:
        assert choice.saved_codex_account_names(tmp_path) == ()

    def should_refuse_an_invalid_name_from_the_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CODEX_ACCOUNT_PROFILES", "alpha,bad name")
        with pytest.raises(ValueError, match="CODEX_ACCOUNT_PROFILES names 'bad name'"):
            choice.saved_codex_account_names(tmp_path)

    @pytest.mark.parametrize("document", [["alpha", "con"], ["alpha", 3], {"alpha": 1}])
    def should_refuse_a_saved_file_with_an_invalid_name(
        self, tmp_path: Path, document: object
    ) -> None:
        save_roster(tmp_path, document)
        with pytest.raises(ValueError, match="account-launchers.json"):
            choice.saved_codex_account_names(tmp_path)

    def should_drop_duplicates_and_keep_the_first_order(self, tmp_path: Path) -> None:
        save_roster(tmp_path, ["beta", "alpha", "beta", "gamma", "alpha"])
        assert choice.saved_codex_account_names(tmp_path) == ("beta", "alpha", "gamma")

    def should_save_the_roster_as_a_json_list_ending_in_a_newline(
        self, tmp_path: Path
    ) -> None:
        profiles_root = tmp_path / "profiles"
        choice.save_codex_account_names(profiles_root, ("alpha", "beta"))
        assert (profiles_root / "account-launchers.json").read_bytes() == (
            b'[\n  "alpha",\n  "beta"\n]\n'
        )
        assert choice.saved_codex_account_names(profiles_root) == ("alpha", "beta")

    def should_fall_back_to_the_four_fixed_accounts_without_a_roster(
        self, tmp_path: Path
    ) -> None:
        assert choice.codex_account_names(tmp_path) == (
            "codex-1",
            "codex-2",
            "codex-3",
            "codex-4",
        )


class TestRosterDrivesTheJobCommands:
    def should_try_the_roster_in_order_and_skip_the_fixed_accounts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        all_weekly_used = {"beta": 95.0, "alpha": 50.0, "codex-1": 0.0}
        for each_name in all_weekly_used:
            (tmp_path / each_name).mkdir()
            (tmp_path / each_name / "auth.json").write_text("{}")
        monkeypatch.setenv("CODEX_ACCOUNT_PROFILES", "beta,alpha")
        monkeypatch.setattr(
            choice,
            "_meter_reader",
            lambda codex_path: (
                lambda codex_home: CodexAccountMeters(
                    (UsageWindow(10080, all_weekly_used[codex_home.name], None),)
                )
            ),
        )
        assert choice.main(["--profiles-root", str(tmp_path), "choose"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert (payload["tier"], payload["account"]) == ("normal", "alpha")
        assert [each["name"] for each in payload["accounts"]] == ["beta", "alpha"]

    def should_choose_among_the_four_fixed_accounts_without_a_roster(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(choice, "_meter_reader", lambda codex_path: None)
        assert choice.main(["--profiles-root", str(tmp_path), "choose"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert [each["name"] for each in payload["accounts"]] == [
            "codex-1",
            "codex-2",
            "codex-3",
            "codex-4",
        ]

    def should_sync_only_the_roster_accounts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        main_home = build_codex_main_home(tmp_path)
        profiles_root = tmp_path / "profiles"
        monkeypatch.setenv("CODEX_ACCOUNT_PROFILES", "alpha")
        all_arguments = ["--profiles-root", str(profiles_root), "sync"]
        assert choice.main([*all_arguments, "--main-home", str(main_home)]) == 0
        assert list(json.loads(capsys.readouterr().out)) == ["alpha"]
        assert links_to(profiles_root / "alpha" / "agents", main_home / "agents")
        assert not (profiles_root / "codex-1").exists()

    def should_check_a_saved_roster_account(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        save_roster(tmp_path, ["alpha"])
        (tmp_path / "alpha").mkdir()
        (tmp_path / "alpha" / "auth.json").write_text("{}")
        monkeypatch.setattr(
            choice,
            "_meter_reader",
            lambda codex_path: (
                lambda codex_home: CodexAccountMeters((UsageWindow(10080, 40.0, None),))
            ),
        )
        assert choice.main(["--profiles-root", str(tmp_path), "check", "alpha"]) == 0

    @pytest.mark.parametrize("account", ["gamma", "codex-1"])
    def should_refuse_to_check_an_account_outside_the_roster(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account: str
    ) -> None:
        save_roster(tmp_path, ["alpha"])
        monkeypatch.setattr(choice, "_meter_reader", lambda codex_path: None)
        with pytest.raises(SystemExit) as exit_info:
            choice.main(["--profiles-root", str(tmp_path), "check", account])
        assert exit_info.value.code == 2


class TestInstallLaunchers:
    def should_link_the_shared_setup_and_keep_each_sign_in_per_account(
        self, tmp_path: Path
    ) -> None:
        main_home = build_codex_main_home(tmp_path)
        report = install(main_home, tmp_path, "alpha", "beta")
        assert list(report) == ["alpha", "beta"]
        for each_name in ("alpha", "beta"):
            each_home = tmp_path / "profiles" / each_name
            for each_entry in ALL_SHARED_ENTRY_NAMES:
                assert links_to(each_home / each_entry, main_home / each_entry)
            for each_local_entry in ("auth.json", "history.jsonl", "sessions"):
                assert not os.path.lexists(each_home / each_local_entry)
            assert report[each_name]["launcher"] == str(
                tmp_path / "bin" / f"codex-{each_name}.cmd"
            )

    def should_change_nothing_on_a_second_run(self, tmp_path: Path) -> None:
        main_home = build_codex_main_home(tmp_path)
        install(main_home, tmp_path, "alpha")
        launcher_path = tmp_path / "bin" / "codex-alpha.cmd"
        first_launcher_bytes = launcher_path.read_bytes()
        second_report = install(main_home, tmp_path, "alpha")
        assert second_report["alpha"]["linked"] == []
        assert second_report["alpha"]["moved_aside"] == []
        assert second_report["alpha"]["unlinked"] == []
        assert launcher_path.read_bytes() == first_launcher_bytes
        assert sorted(each.name for each in (tmp_path / "bin").iterdir()) == [
            "codex-alpha.cmd"
        ]

    def should_set_codex_home_and_call_codex_in_the_launcher(
        self, tmp_path: Path
    ) -> None:
        install(build_codex_main_home(tmp_path), tmp_path, "alpha")
        launcher_lines = (tmp_path / "bin" / "codex-alpha.cmd").read_bytes().split(b"\r\n")
        profile_home = tmp_path / "profiles" / "alpha"
        assert f'set "CODEX_HOME={profile_home}"'.encode() in launcher_lines
        assert b"call codex %*" in launcher_lines

    def should_install_the_environment_roster_from_the_command_line(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        main_home = build_codex_main_home(tmp_path)
        save_roster(tmp_path / "profiles", ["gamma"])
        monkeypatch.setenv("CODEX_ACCOUNT_PROFILES", "beta")
        all_arguments = [
            "--profiles-root",
            str(tmp_path / "profiles"),
            "install",
            "--main-home",
            str(main_home),
            "--launcher-directory",
            str(tmp_path / "bin"),
        ]
        assert choice.main(all_arguments) == 0
        assert list(json.loads(capsys.readouterr().out)) == ["beta"]
        assert (tmp_path / "bin" / "codex-beta.cmd").is_file()
        assert not (tmp_path / "bin" / "codex-gamma.cmd").exists()

    def should_print_an_empty_report_for_an_empty_roster(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        all_arguments = ["--profiles-root", str(tmp_path / "profiles"), "install"]
        assert choice.main([*all_arguments, "--launcher-directory", str(tmp_path / "bin")]) == 0
        assert json.loads(capsys.readouterr().out) == {}
        assert not (tmp_path / "bin").exists()


class TestSetupRoster:
    def should_save_each_valid_name_once_in_typed_order(self, tmp_path: Path) -> None:
        all_shown: list[str] = []
        all_names, all_retired = choice.update_codex_account_roster(
            profiles_root=tmp_path,
            launcher_directory=tmp_path / "bin",
            now=NOW,
            read_line=typed_lines("alpha", "bad name", "alpha", "beta", "", "gamma"),
            write_line=all_shown.append,
        )
        assert (all_names, all_retired) == (("alpha", "beta"), {})
        assert choice.saved_codex_account_names(tmp_path) == ("alpha", "beta")
        assert all_shown == [
            "Saved Codex account launchers: none",
            "profile name must use letters, digits, hyphens, or underscores",
        ]

    def should_finish_at_the_end_of_input(self, tmp_path: Path) -> None:
        all_names, _ = choice.update_codex_account_roster(
            profiles_root=tmp_path,
            launcher_directory=tmp_path / "bin",
            now=NOW,
            read_line=typed_lines("gamma"),
            write_line=lambda line: None,
        )
        assert all_names == ("gamma",)

    def should_move_a_dropped_launcher_aside_and_keep_its_home(
        self, tmp_path: Path
    ) -> None:
        main_home = build_codex_main_home(tmp_path)
        profiles_root = tmp_path / "profiles"
        choice.save_codex_account_names(profiles_root, ("alpha", "beta"))
        install(main_home, tmp_path, "alpha", "beta")
        (profiles_root / "beta" / "auth.json").write_text("beta sign-in", encoding="utf-8")
        all_shown: list[str] = []
        all_names, all_retired = choice.update_codex_account_roster(
            profiles_root=profiles_root,
            launcher_directory=tmp_path / "bin",
            now=NOW,
            read_line=typed_lines("alpha", ""),
            write_line=all_shown.append,
        )
        moved_launcher = tmp_path / "bin" / "codex-beta.cmd.replaced-20260923T170000Z"
        assert all_names == ("alpha",)
        assert all_retired == {"beta": str(moved_launcher)}
        assert all_shown == ["Saved Codex account launchers: alpha, beta"]
        assert moved_launcher.is_file()
        assert not (tmp_path / "bin" / "codex-beta.cmd").exists()
        assert (tmp_path / "bin" / "codex-alpha.cmd").is_file()
        assert (profiles_root / "beta" / "auth.json").read_text(encoding="utf-8") == (
            "beta sign-in"
        )
        assert choice.saved_codex_account_names(profiles_root) == ("alpha",)


class TestCodexLauncher:
    @pytest.mark.skipif(os.name != "nt", reason="runs the launcher through cmd.exe")
    def should_hand_codex_home_to_the_npm_codex_shim(self, tmp_path: Path) -> None:
        profile_home = tmp_path / "profiles" / "alpha"
        launcher_path = write_launcher(
            launcher_directory=tmp_path / "bin",
            profile_home=profile_home,
            now=NOW,
            profile_name="alpha",
            launcher_file_name_template=CODEX_LAUNCHER_FILE_NAME_TEMPLATE,
            launcher_text_template=CODEX_LAUNCHER_TEXT_TEMPLATE,
        )
        fake_directory = tmp_path / "fake"
        fake_directory.mkdir()
        (fake_directory / "codex.cmd").write_bytes(NPM_CODEX_SHIM_TEXT.encode("utf-8"))
        environment = dict(os.environ)
        environment["PATH"] = str(fake_directory) + os.pathsep + environment["PATH"]
        environment["CODEX_HOME"] = str(tmp_path / "decoy")
        completed = subprocess.run(
            ["cmd", "/c", str(launcher_path)],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.stdout.strip() == str(profile_home)
