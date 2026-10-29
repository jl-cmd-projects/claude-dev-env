"""The instruction budget check counts launch bytes, finds named people, and limits link nesting."""

import hashlib
import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).parents[1]
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from dev_env_scripts_constants.followup_constants import (
    GATE_FAILED_EXIT_CODE,
    GATE_PASSED_EXIT_CODE,
    INSTRUCTION_BUDGET_RULE_ID,
    INSTRUCTION_NESTING_RULE_ID,
    INSTRUCTION_PERSONAL_NAME_RULE_ID,
)
from dev_env_scripts_constants.instruction_budget_constants import (
    INSTRUCTION_BUDGET_CONFIG_FILE_NAME,
    PASSED_MESSAGE,
)
from dev_env_scripts_constants.private_term_constants import PrivateTermDigest
from instruction_budget import check_repository, main
from instruction_budget_files import (
    InstructionBudgetConfig,
    budget_findings,
    instruction_files,
    is_instruction_file,
    launch_files,
    load_config,
    measure_launch_bytes,
)
from instruction_budget_links import hop_distances, nesting_findings
from instruction_budget_names import personal_name_findings, personal_name_line_numbers

FIXTURE_NAME = "zorbel"
FIXTURE_DIGESTS = frozenset(
    {
        PrivateTermDigest(
            length=len(FIXTURE_NAME),
            sha256=hashlib.sha256(FIXTURE_NAME.encode("utf-8")).hexdigest(),
        )
    }
)


def _config(
    max_launch_bytes: int = 10**9,
    max_link_hops: int = 2,
    rules_dirs: tuple[str, ...] = (),
) -> InstructionBudgetConfig:
    return InstructionBudgetConfig(
        max_launch_bytes=max_launch_bytes,
        max_link_hops=max_link_hops,
        rules_dirs=rules_dirs,
    )


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_budget_file(repository_root: Path, config_text: str) -> None:
    _write(repository_root / INSTRUCTION_BUDGET_CONFIG_FILE_NAME, config_text)


def test_load_config_returns_none_without_a_budget_file(tmp_path: Path) -> None:
    assert load_config(tmp_path) is None


def test_load_config_reads_the_cap_hops_and_rule_folders(tmp_path: Path) -> None:
    _write_budget_file(
        tmp_path,
        '{"max_launch_bytes": 1200, "max_link_hops": 3, "rules_dirs": ["shared/rules"]}',
    )
    assert load_config(tmp_path) == InstructionBudgetConfig(
        max_launch_bytes=1200, max_link_hops=3, rules_dirs=("shared/rules",)
    )


def test_launch_files_follow_imports_and_skip_scoped_rules(tmp_path: Path) -> None:
    _write(tmp_path / "CLAUDE.md", "@AGENTS.md\n")
    _write(tmp_path / "AGENTS.md", "# Root\n")
    _write(tmp_path / ".claude" / "rules" / "always.md", "# Always\n")
    _write(
        tmp_path / ".claude" / "rules" / "scoped.md",
        '---\npaths:\n  - "**/*.py"\n---\n\n# Scoped\n',
    )
    all_launch = {
        each_path.relative_to(tmp_path.resolve()).as_posix()
        for each_path in launch_files(tmp_path.resolve(), _config())
    }
    assert all_launch == {"CLAUDE.md", "AGENTS.md", ".claude/rules/always.md"}


def test_budget_passes_at_the_cap_and_fails_one_byte_over(tmp_path: Path) -> None:
    _write(tmp_path / "AGENTS.md", "x" * 100)
    repository_root = tmp_path.resolve()
    assert measure_launch_bytes(repository_root, _config()) == 100
    assert budget_findings(repository_root, _config(max_launch_bytes=100)) == []
    over_findings = budget_findings(repository_root, _config(max_launch_bytes=99))
    assert [each.rule_id for each in over_findings] == [INSTRUCTION_BUDGET_RULE_ID]
    assert "100" in over_findings[0].message and "99" in over_findings[0].message


def test_personal_name_line_numbers_match_whole_words_only() -> None:
    text = "zorbel-kit\nzorbels and zorbelish\nsee zorbel's notes\n"
    assert personal_name_line_numbers(text, FIXTURE_DIGESTS) == (1, 3)


def test_personal_name_line_numbers_flag_the_named_people() -> None:
    text = "Intro line.\nJon wrote this.\nMelanie reviewed it.\n"
    assert personal_name_line_numbers(text) == (2, 3)


def test_personal_name_findings_name_lines_but_not_the_name(tmp_path: Path) -> None:
    path = _write(tmp_path / "AGENTS.md", "first\nzorbel here\n")
    all_findings = personal_name_findings(
        tmp_path.resolve(), [path.resolve()], FIXTURE_DIGESTS
    )
    assert len(all_findings) == 1
    assert all_findings[0].rule_id == INSTRUCTION_PERSONAL_NAME_RULE_ID
    assert "line(s) 2" in all_findings[0].message
    assert FIXTURE_NAME not in all_findings[0].message


def test_hop_distances_count_the_fewest_links_from_a_root(tmp_path: Path) -> None:
    repository_root = tmp_path.resolve()
    root_path = _write(repository_root / "AGENTS.md", "[one](one.md)\n")
    _write(repository_root / "one.md", "[two](two.md)\n")
    _write(repository_root / "two.md", "[three](three.md)\n")
    _write(repository_root / "three.md", "# Three\n")
    _write(repository_root / "orphan.md", "# Orphan\n")
    distances = hop_distances(repository_root, [root_path.resolve()])
    assert distances[repository_root / "AGENTS.md"] == 0
    assert distances[repository_root / "two.md"] == 2
    assert distances[repository_root / "three.md"] == 3
    assert repository_root / "orphan.md" not in distances


def test_hop_distances_ignore_fenced_blocks_and_external_links(tmp_path: Path) -> None:
    repository_root = tmp_path.resolve()
    root_path = _write(
        repository_root / "AGENTS.md",
        "[site](https://example.com/page.md)\n"
        "[section](#top)\n"
        "```\n[hidden](hidden.md)\n```\n"
        "[shown](shown.md)\n",
    )
    _write(repository_root / "hidden.md", "# Hidden\n")
    _write(repository_root / "shown.md", "# Shown\n")
    distances = hop_distances(repository_root, [root_path.resolve()])
    assert repository_root / "shown.md" in distances
    assert repository_root / "hidden.md" not in distances


def test_nesting_findings_flag_only_scoped_files_beyond_the_cap(tmp_path: Path) -> None:
    repository_root = tmp_path.resolve()
    _write(repository_root / "AGENTS.md", "[one](one.md)\n")
    _write(repository_root / "one.md", "[two](two.md)\n")
    _write(repository_root / "two.md", "[three](three.md)\n")
    _write(repository_root / "three.md", "# Three\n")
    all_findings = nesting_findings(
        repository_root,
        _config(max_link_hops=2),
        [repository_root / "two.md", repository_root / "three.md"],
    )
    assert [each.file_path for each in all_findings] == ["three.md"]
    assert all_findings[0].rule_id == INSTRUCTION_NESTING_RULE_ID


def test_fenced_import_line_is_not_followed(tmp_path: Path) -> None:
    repository_root = tmp_path.resolve()
    root_path = _write(
        repository_root / "AGENTS.md",
        "```\n@docs/fenced/AGENTS.md\n```\n",
    )
    fenced_path = _write(
        repository_root / "docs" / "fenced" / "AGENTS.md", "# Fenced\n"
    )
    distances = hop_distances(repository_root, [root_path.resolve()])
    assert fenced_path.resolve() not in distances
    assert fenced_path.resolve() not in launch_files(repository_root, _config())


def test_personal_name_line_numbers_skip_underscore_identifiers() -> None:
    assert personal_name_line_numbers("use zorbel_helper here\n", FIXTURE_DIGESTS) == ()


def test_is_instruction_file_covers_entry_skill_and_rule_files(tmp_path: Path) -> None:
    repository_root = tmp_path.resolve()
    config = _config(rules_dirs=("shared/rules",))
    assert is_instruction_file(repository_root / "AGENTS.md", repository_root, config)
    assert is_instruction_file(
        repository_root / "skills" / "x" / "SKILL.md", repository_root, config
    )
    assert is_instruction_file(
        repository_root / ".claude" / "rules" / "a.md", repository_root, config
    )
    assert is_instruction_file(
        repository_root / "shared" / "rules" / "b.md", repository_root, config
    )
    assert not is_instruction_file(
        repository_root / "docs" / "guide.md", repository_root, config
    )


def test_check_repository_skips_changed_files_that_are_not_instruction_files(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path.resolve()
    guide_path = _write(repository_root / "docs" / "guide.md", "zorbel\n")
    assert check_repository(repository_root, _config(), [guide_path.resolve()]) == []


def test_instruction_files_lists_the_whole_tree(tmp_path: Path) -> None:
    repository_root = tmp_path.resolve()
    _write(repository_root / "AGENTS.md", "# Root\n")
    _write(repository_root / "pkg" / "CLAUDE.md", "# Nested\n")
    _write(repository_root / "docs" / "guide.md", "# Guide\n")
    all_relative = {
        each_path.relative_to(repository_root).as_posix()
        for each_path in instruction_files(repository_root, _config())
    }
    assert all_relative == {"AGENTS.md", "pkg/CLAUDE.md"}


def test_main_fails_when_the_repository_has_no_budget_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["--repository-root", str(tmp_path), "--all-files"])
        == GATE_FAILED_EXIT_CODE
    )
    assert INSTRUCTION_BUDGET_CONFIG_FILE_NAME in capsys.readouterr().out


def test_main_passes_a_clean_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_budget_file(tmp_path, '{"max_launch_bytes": 1000}')
    _write(tmp_path / "AGENTS.md", "# Clean\n")
    assert (
        main(["--repository-root", str(tmp_path), "--all-files"])
        == GATE_PASSED_EXIT_CODE
    )
    assert capsys.readouterr().out.strip() == PASSED_MESSAGE


def test_main_fails_an_over_budget_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_budget_file(tmp_path, '{"max_launch_bytes": 10}')
    _write(tmp_path / "AGENTS.md", "x" * 50)
    assert (
        main(["--repository-root", str(tmp_path), "--all-files"])
        == GATE_FAILED_EXIT_CODE
    )
    assert f"[{INSTRUCTION_BUDGET_RULE_ID}]" in capsys.readouterr().out
