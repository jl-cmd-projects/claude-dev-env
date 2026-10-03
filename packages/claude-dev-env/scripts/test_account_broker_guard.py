from __future__ import annotations

import ast
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
ALLOWED_LEGACY_MODULES = frozenset(
    {
        "claude_account_choice.py",
        "claude_account_worker.py",
        "claude_chain_runner.py",
        "claude_chain_usage.py",
        "codex_account_choice.py",
        "codex_account_meters.py",
    }
)
ACCOUNT_LIST_CALLS = frozenset(
    {
        "load_chain",
        "extra_config_directories",
        "read_extra_accounts",
        "codex_account_names",
        "saved_codex_account_names",
    }
)
ACCOUNT_LIST_MARKERS = frozenset(
    {
        "claude-chain.json",
        "extra-profiles.json",
        "account-launchers.json",
        "EXTRA_PROFILES_FILE_NAME",
        "CODEX_ACCOUNT_LAUNCHERS_FILE_NAME",
    }
)
ACCOUNT_ENVIRONMENT_MARKERS = frozenset(
    {
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR_ENV_VAR",
        "CODEX_HOME_ENVIRONMENT_VARIABLE",
    }
)


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _sets_account_home(node: ast.AST) -> bool:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = (node.target,)
    else:
        return False
    for target in targets:
        if isinstance(target, ast.Subscript) and any(
            marker in ast.unparse(target.slice) for marker in ACCOUNT_ENVIRONMENT_MARKERS
        ):
            return True
    return False


def _reads_account_list(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _called_name(node) in ACCOUNT_LIST_CALLS:
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = ast.unparse(node)
            if "read_text" in body and any(
                marker in body for marker in ACCOUNT_LIST_MARKERS
            ):
                return True
    return False


def _chooses_account_in_module(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if _reads_account_list(tree):
        return True
    for node in ast.walk(tree):
        if _sets_account_home(node):
            return True
        if isinstance(node, ast.Dict) and any(
            key is not None
            and any(marker in ast.unparse(key) for marker in ACCOUNT_ENVIRONMENT_MARKERS)
            for key in node.keys
        ):
            return True
    return False


def test_should_reject_new_account_pickers_outside_broker() -> None:
    all_pickers = {
        path.name
        for path in SCRIPTS.rglob("*.py")
        if not path.name.startswith("test_")
        and "tests" not in path.parts
        and _chooses_account_in_module(path)
    }

    assert all_pickers <= ALLOWED_LEGACY_MODULES | {"account_broker.py"}
