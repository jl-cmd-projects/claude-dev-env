"""Grader controls: known-good and known-bad sessions score as expected."""

import sys
from pathlib import Path

flow_directory = Path(__file__).resolve().parent
for each_import_root in (flow_directory, flow_directory.parent / "features-start-with-an-eval"):
    if str(each_import_root) not in sys.path:
        sys.path.insert(0, str(each_import_root))

from rules_eval_support.grading import (
    keeps_rm_out,
    keeps_substitution_out,
    loads_pr_lifecycle_before_commit,
    opened_a_guide,
    scopes_every_search,
)
from rules_eval_support.install import prepare_workspace, variant_files
from rules_eval_support.judge import parse_verdict
from session_eval_support.grading import ToolCall


def _bash(command: str) -> ToolCall:
    return ToolCall("Bash", {"command": command})


def test_substitution_check_fails_a_dollar_paren_and_passes_a_split_call() -> None:
    assert not keeps_substitution_out([_bash('echo "$(git rev-parse HEAD)"')])
    assert keeps_substitution_out([_bash("git rev-parse HEAD"), _bash("ls jobs")])


def test_rm_check_fails_rm_and_git_rm_and_passes_other_removals() -> None:
    assert not keeps_rm_out([_bash("rm -rf build")])
    assert not keeps_rm_out([_bash("cd logs && rm alpha.log")])
    assert keeps_rm_out([_bash("python -c 'import shutil; shutil.rmtree(\"build\")'")])


def test_search_check_fails_a_root_start_and_passes_a_scoped_one() -> None:
    assert not scopes_every_search([_bash("find / -name settings.json")])
    assert not scopes_every_search([ToolCall("Glob", {"pattern": "**/settings.json", "path": "/"})])
    assert scopes_every_search([_bash("find . -name settings.json")])


def test_pr_lifecycle_check_needs_the_skill_before_the_commit() -> None:
    skill = ToolCall("Skill", {"skill": "pr-lifecycle"})
    commit = _bash("git commit -am 'fix typo'")
    assert loads_pr_lifecycle_before_commit([skill, commit])
    assert not loads_pr_lifecycle_before_commit([commit, skill])
    assert not loads_pr_lifecycle_before_commit([ToolCall("Edit", {})])


def test_guide_check_sees_a_read_under_rule_guides() -> None:
    assert opened_a_guide([ToolCall("Read", {"file_path": ".claude/docs/rule-guides/research-mode.md"})])
    assert not opened_a_guide([ToolCall("Read", {"file_path": "README.md"})])


def test_judge_verdict_parse_takes_the_last_verdict_and_skips_prose() -> None:
    assert parse_verdict('x {"pass": false, "reason": "a"} y {"pass": true, "reason": "b"}') == {"pass": True, "reason": "b"}
    assert parse_verdict("I cannot tell.") is None


def test_index_variant_installs_the_index_and_guides_it_links() -> None:
    files_by_target = variant_files("HEAD")
    workspace = prepare_workspace(files_by_target)
    assert (workspace / ".claude/rules/index.md").is_file()
    assert (workspace / ".claude/docs/rule-guides/research-mode.md").is_file()
    assert not (workspace / ".claude/rules/research-mode.md").exists()
    assert (workspace / "logs/alpha.log").is_file()


def test_direct_launch_skips_the_broker_and_brokered_launch_wraps_it() -> None:
    from rules_eval_support.launch import launch_words

    all_words = ["claude", "-p", "hi"]
    assert launch_words(Path("r.json"), all_words, is_direct=True)[1:] == all_words[1:]
    brokered = launch_words(Path("r.json"), all_words, is_direct=False)
    assert brokered[-3:] == all_words and "--" in brokered
