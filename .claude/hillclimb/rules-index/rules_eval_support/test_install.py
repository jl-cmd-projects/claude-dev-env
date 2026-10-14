from rules_eval_support import install


def test_variant_files_keeps_unscoped_rules_and_all_guides(monkeypatch) -> None:
    sources = {
        "HEAD:packages/claude-dev-env/rules": "index.md\nscoped.md\n",
        "HEAD:packages/claude-dev-env/docs/rule-guides": "guide.md\n",
        "HEAD:packages/claude-dev-env/rules/index.md": "Always loaded.\n",
        "HEAD:packages/claude-dev-env/rules/scoped.md": "---\npaths: src/**\n---\nScoped.\n",
        "HEAD:packages/claude-dev-env/docs/rule-guides/guide.md": "Guide.\n",
    }
    monkeypatch.setattr(install, "_read_git", lambda *args: sources[args[-1]])

    assert install.variant_files("HEAD") == {
        ".claude/rules/index.md": "Always loaded.\n",
        ".claude/docs/rule-guides/guide.md": "Guide.\n",
    }
