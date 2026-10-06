"""Hold changed agent context files and the over-budget list to the context budget.

The budget core lives in ``hooks/context_budget``, shared with the write hook.
The policy is ``.claude/context-budget.json`` at the repository root; a
repository without one is not checked.

::

    context-budget         SKILL.md over its limit grew    -> finding
    context-budget-policy  baseline entry raised           -> finding
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from types import ModuleType

from .adapter_support import HookModuleLoader
from .config import constants
from .model import Diagnostic, Document, DocumentSet, Severity


def accepts_context_markdown(document: Document) -> bool:
    """Return whether the document is Markdown the kind table may select.

    Args:
        document: Candidate document.

    Returns:
        True for Markdown documents.
    """
    return document.path.suffix.lower() in constants.ALL_MARKDOWN_SUFFIXES


def accepts_context_budget_policy(document: Document) -> bool:
    """Return whether the document is the repository's budget policy file.

    Args:
        document: Candidate document.

    Returns:
        True for ``.claude/context-budget.json``.
    """
    return document.path.as_posix() == constants.CONTEXT_BUDGET_POLICY_PATH


def _file_diagnostic(rule_id: str, message: str) -> Diagnostic:
    return Diagnostic(rule_id, Severity.ERROR, message)


def context_budget_diagnostics(
    document: Document, repository_root: Path, load_module: HookModuleLoader
) -> tuple[Diagnostic, ...]:
    """Report the budget findings of one changed context file.

    Args:
        document: Current text and the prior text the ratchet compares.
        repository_root: Repository root holding the policy file.
        load_module: Hook module loader.

    Returns:
        One diagnostic per finding; empty without a readable policy file.
    """
    policy_file = load_module(constants.CONTEXT_BUDGET_POLICY_FILE_MODULE)
    model = load_module(constants.CONTEXT_BUDGET_MODEL_MODULE)
    try:
        policy = policy_file.read_policy_file(repository_root)
    except model.ContextBudgetPolicyError:
        return ()
    if policy is None:
        return ()
    findings = load_module(constants.CONTEXT_BUDGET_FINDINGS_MODULE)
    all_findings = findings.file_findings(
        policy, document.path.as_posix(), document.text, document.prior_text
    )
    return tuple(
        _file_diagnostic(constants.CONTEXT_BUDGET_RULE_ID, each.message)
        for each in all_findings
    )


def _prior_policy(prior_text: str | None, policy_file: ModuleType, model: ModuleType) -> object:
    if prior_text is None:
        return None
    try:
        return policy_file.parse_policy(prior_text)
    except model.ContextBudgetPolicyError:
        return None


def _policy_messages(document: Document, load_module: HookModuleLoader) -> list[str]:
    policy_file = load_module(constants.CONTEXT_BUDGET_POLICY_FILE_MODULE)
    model = load_module(constants.CONTEXT_BUDGET_MODEL_MODULE)
    policy_path = document.path.as_posix()
    try:
        current_policy = policy_file.parse_policy(document.text)
    except model.ContextBudgetPolicyError as error:
        all_messages = [
            constants.CONTEXT_BUDGET_UNREADABLE_MESSAGE.format(path=policy_path, error=error)
        ]
    else:
        prior_policy = _prior_policy(document.prior_text, policy_file, model)
        policy_changes = load_module(constants.CONTEXT_BUDGET_POLICY_CHANGES_MODULE)
        all_messages = [
            each.message
            for each in policy_changes.policy_shrink_findings(
                policy_path, prior_policy, current_policy
            )
        ]
    return all_messages


def context_budget_policy_diagnostics(
    document: Document, repository_root: Path, load_module: HookModuleLoader
) -> tuple[Diagnostic, ...]:
    """Report each change to the policy file that loosens the budget.

    Args:
        document: Current policy text and its prior text.
        repository_root: Repository root, unused by this check.
        load_module: Hook module loader.

    Returns:
        One diagnostic per loosening change, or one for an unparseable file.
    """
    del repository_root
    rule_id = constants.CONTEXT_BUDGET_POLICY_RULE_ID
    all_messages = _policy_messages(document, load_module)
    return tuple(_file_diagnostic(rule_id, each) for each in all_messages)


def context_budget_policy_change_set_diagnostics(
    document_set: DocumentSet,
) -> tuple[Diagnostic, ...]:
    """Reject removal or movement of the policy path in a Git selection.

    Args:
        document_set: Changed documents and removed or renamed paths.

    Returns:
        One finding when the selection removes the policy path.
    """
    policy_path = PurePosixPath(constants.CONTEXT_BUDGET_POLICY_PATH)
    removed_paths = set(document_set.deleted_paths)
    removed_paths.update(
        old_path for old_path, new_path in document_set.renamed_paths if old_path != new_path
    )
    if policy_path not in removed_paths:
        return ()
    return (
        Diagnostic(
            constants.CONTEXT_BUDGET_POLICY_RULE_ID,
            Severity.ERROR,
            constants.CONTEXT_BUDGET_POLICY_REMOVED_MESSAGE.format(path=policy_path),
            check_id=constants.CONTEXT_BUDGET_POLICY_REMOVAL_RULE_ID,
        ),
    )
