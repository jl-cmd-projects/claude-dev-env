"""Tests for Codex account rosters, homes, and launchers."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

import codex_account_choice as choice
from claude_account_profile import links_to

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
        (main_home / "trimmed-sol.config.toml").write_text("model = 'y'")
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
        assert os.readlink(each_home / "trimmed-sol.config.toml") == str(
            main_home / "trimmed-sol.config.toml"
        )
        assert not (each_home / "auth.json").exists()
        assert not (each_home / "sessions").exists()


class TestSmallHelpers:
    @pytest.mark.parametrize(
        ("entry_name", "is_local"),
        [("auth.json", True), ("sessions", True), ("state_5.sqlite", True), ("config.toml", False), ("trimmed-sol.config.toml", False), ("plugins", False), ("agents", False)],
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


class TestAccountRoster:
    @pytest.mark.parametrize("command", ["choose", "check"])
    def test_should_reject_removed_choice_commands(self, command: str) -> None:
        with pytest.raises(SystemExit) as exit_info:
            choice.main([command])
        assert exit_info.value.code == 2

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

    def test_should_refuse_a_saved_file_that_is_not_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "account-launchers.json").write_text('["alpha",', encoding="utf-8")
        with pytest.raises(SystemExit) as exit_info:
            choice.main(["--profiles-root", str(tmp_path), "sync"])
        assert exit_info.value.code == 2
        assert "account-launchers.json" in capsys.readouterr().err

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


class TestRosterDrivesTheSyncCommand:
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
