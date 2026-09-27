import json
import sys
from pathlib import Path

import pytest

scripts_directory = str(Path(__file__).resolve().parent)
if scripts_directory not in sys.path:
    sys.path.insert(0, scripts_directory)

import link_plugin_skills

PLUGIN_KEY = "kit@market"


def install_plugin(
    claude_home: Path, version: str, all_skill_names: tuple[str, ...]
) -> Path:
    install_path = claude_home / "plugins" / "cache" / "market" / "kit" / version
    for each_name in all_skill_names:
        skill_directory = install_path / "skills" / each_name
        skill_directory.mkdir(parents=True)
        (skill_directory / "SKILL.md").write_text("---\nname: x\n---\n")
    record = {
        "installPath": str(install_path),
        "version": version,
        "lastUpdated": version,
    }
    (claude_home / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {PLUGIN_KEY: [record]}})
    )
    return install_path


def enable_plugin(claude_home: Path, is_enabled: bool) -> None:
    (claude_home / "settings.json").write_text(
        json.dumps({"enabledPlugins": {PLUGIN_KEY: is_enabled}})
    )


@pytest.fixture
def claude_home(tmp_path: Path) -> Path:
    home = tmp_path / ".claude"
    (home / "plugins").mkdir(parents=True)
    agents_skills = tmp_path / ".agents" / "skills"
    agents_skills.mkdir(parents=True)
    (home / "skills").symlink_to(agents_skills, target_is_directory=True)
    enable_plugin(home, True)
    return home


def run_sync(claude_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys, "argv", ["link_plugin_skills.py", "--claude-home", str(claude_home)]
    )
    link_plugin_skills.main()


def test_should_link_each_plugin_skill_through_the_skills_pointer(
    claude_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_path = install_plugin(claude_home, "1.0.0", ("tdd", "how"))

    run_sync(claude_home, monkeypatch)

    assert (claude_home / "skills" / "tdd").resolve() == install_path / "skills" / "tdd"
    assert (claude_home / "skills" / "how" / "SKILL.md").is_file()


def test_should_leave_an_existing_skill_of_the_same_name_untouched(
    claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install_plugin(claude_home, "1.0.0", ("tdd",))
    own_skill = claude_home / "skills" / "tdd"
    own_skill.mkdir()
    (own_skill / "SKILL.md").write_text("mine")

    run_sync(claude_home, monkeypatch)

    assert not own_skill.is_symlink()
    assert (own_skill / "SKILL.md").read_text() == "mine"
    assert "skipped tdd" in capsys.readouterr().out


def test_should_repoint_links_and_drop_vanished_skills_when_the_version_changes(
    claude_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_plugin(claude_home, "1.0.0", ("tdd", "old"))
    run_sync(claude_home, monkeypatch)
    new_install_path = install_plugin(claude_home, "2.0.0", ("tdd",))

    run_sync(claude_home, monkeypatch)

    assert (
        claude_home / "skills" / "tdd"
    ).resolve() == new_install_path / "skills" / "tdd"
    assert not (claude_home / "skills" / "old").is_symlink()


def test_should_remove_owned_links_when_the_plugin_is_disabled(
    claude_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_plugin(claude_home, "1.0.0", ("tdd",))
    run_sync(claude_home, monkeypatch)
    enable_plugin(claude_home, False)

    run_sync(claude_home, monkeypatch)

    assert list((claude_home / "skills").iterdir()) == []


def test_should_keep_a_user_link_that_points_outside_the_plugin_cache(
    claude_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_plugin(claude_home, "1.0.0", ())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    user_link = claude_home / "skills" / "mine"
    user_link.symlink_to(elsewhere, target_is_directory=True)

    run_sync(claude_home, monkeypatch)

    assert user_link.resolve() == elsewhere


def test_should_change_nothing_on_a_second_run(
    claude_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install_plugin(claude_home, "1.0.0", ("tdd", "how"))
    run_sync(claude_home, monkeypatch)
    capsys.readouterr()

    run_sync(claude_home, monkeypatch)

    assert (
        capsys.readouterr().out.strip()
        == "0 linked, 0 re-pointed, 0 removed, 0 skipped, 2 unchanged"
    )
