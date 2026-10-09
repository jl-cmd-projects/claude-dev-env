"""Which rules load in every session, and how skill-scoped rules still reach their skill."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
RULES_DIRECTORY = PACKAGE_ROOT / "rules"
SKILLS_DIRECTORY = PACKAGE_ROOT / ".agents" / "skills"

ALWAYS_ON_RULE_NAMES = frozenset(
    {
        "asd-ste100-language.md",
        "cleanup-temp-files.md",
        "correction-lens.md",
        "destructive-commands.md",
        "explore-thoroughly.md",
        "filesystem-search.md",
        "memory-stores-durable-facts.md",
        "no-contrast-framing.md",
        "proof-before-pull-request.md",
        "question-presentation.md",
        "research-mode.md",
        "request-scope.md",
        "session-title.md",
        "skill-pointers.md",
        "shell-invocation.md",
        "verify-before-asking.md",
        "verify-runtime-state.md",
    }
)

SKILL_SCOPED_RULES = {
    "long-horizon-autonomy.md": ("orchestrator", "orchestrator-refresh"),
    "workers-done-before-complete.md": ("orchestrator", "orchestrator-refresh"),
}


def _declares_paths(rule_path: Path) -> bool:
    lines = rule_path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return False
    for each_line in lines[1:]:
        if each_line == "---":
            return False
        if each_line.startswith("paths:"):
            return True
    return False


def test_only_allowlisted_rules_load_in_every_session() -> None:
    unscoped_rule_names = {
        each_rule.name
        for each_rule in RULES_DIRECTORY.glob("*.md")
        if not _declares_paths(each_rule)
    }
    assert unscoped_rule_names == ALWAYS_ON_RULE_NAMES


def test_skill_scoped_rules_carry_paths_on_their_skill_directories() -> None:
    for each_rule_name, all_skill_names in SKILL_SCOPED_RULES.items():
        rule_text = (RULES_DIRECTORY / each_rule_name).read_text(encoding="utf-8")
        assert _declares_paths(RULES_DIRECTORY / each_rule_name)
        for each_skill_name in all_skill_names:
            assert f'"**/skills/{each_skill_name}/**"' in rule_text


def test_each_scoping_skill_tells_the_agent_to_read_its_rules() -> None:
    for each_rule_name, all_skill_names in SKILL_SCOPED_RULES.items():
        for each_skill_name in all_skill_names:
            skill_text = (SKILLS_DIRECTORY / each_skill_name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            assert f"~/.claude/rules/{each_rule_name}" in skill_text
