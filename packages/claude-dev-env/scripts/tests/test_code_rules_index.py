"""Keep the code-rules index and its feature map in sync with enforcement."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

import pytest


_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _PACKAGE_ROOT.parent.parent
_INDEX_PATH = _PACKAGE_ROOT / "docs" / "CODE_RULES.md"
_FAMILY_DIRECTORY = _PACKAGE_ROOT / "docs" / "code-rules"
_ENFORCER_PATH = _PACKAGE_ROOT / "hooks" / "blocking" / "code_rules_enforcer.py"
_CITATION_ROOTS = (
    _PACKAGE_ROOT / "hooks",
    _PACKAGE_ROOT / "scripts",
    _PACKAGE_ROOT / "docs",
    _PACKAGE_ROOT / "rules",
    _PACKAGE_ROOT / ".agents",
    _REPOSITORY_ROOT / ".cursor",
)
_TEXT_SUFFIXES = frozenset({".md", ".py", ".js", ".mjs", ".ts", ".json", ".xml"})
_MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)\s]+)(?:\s+[^)]*)?\)")
_INDEX_ANCHOR = re.compile(r"CODE_RULES\.md#([^\s)\]<>\"`]+)", re.IGNORECASE)
_NUMBERED_CITATION = re.compile(
    r"(?:CODE_RULES\s*\u00a7\s*|\bsection\s+)(\d+(?:\.\d+)?)", re.IGNORECASE
)


def _heading_slugs(markdown_text: str) -> set[str]:
    all_slugs: set[str] = set()
    slug_counts: Counter[str] = Counter()
    for each_heading in re.findall(r"^#{1,6}\s+(.+)$", markdown_text, re.MULTILINE):
        heading_words = re.sub(r"[^\w\- ]", "", each_heading.lower())
        base_slug = re.sub(r"\s", "-", heading_words)
        count = slug_counts[base_slug]
        all_slugs.add(base_slug if count == 0 else f"{base_slug}-{count}")
        slug_counts[base_slug] += 1
    return all_slugs


def _index_numbers(index_text: str) -> set[str]:
    all_numbers: set[str] = set()
    for each_heading in re.findall(r"^#{1,6}\s+(.+)$", index_text, re.MULTILINE):
        all_numbers.update(
            re.findall(r"(?<!\d)(\d+(?:\.\d+)?)(?=\.?\s|$)", each_heading)
        )
    return all_numbers


def _assert_citations_resolve(
    index_text: str, all_citations: list[tuple[Path, str]]
) -> None:
    valid_slugs = _heading_slugs(index_text)
    valid_numbers = _index_numbers(index_text)
    for each_path, each_text in all_citations:
        for each_anchor in _INDEX_ANCHOR.findall(each_text):
            assert each_anchor in valid_slugs, f"{each_path}: dead CODE_RULES anchor #{each_anchor}"
        for each_number in _NUMBERED_CITATION.findall(each_text):
            normalized_number = ".".join(
                str(int(each_part)) for each_part in each_number.split(".")
            )
            assert normalized_number in valid_numbers, (
                f"{each_path}: dead CODE_RULES section {each_number}"
            )


def test_should_assign_each_enforcer_check_to_one_family() -> None:
    enforcer_tree = ast.parse(_ENFORCER_PATH.read_text(encoding="utf-8"))
    imported_checks = Counter(
        each_name.name
        for each_import in enforcer_tree.body
        if isinstance(each_import, ast.ImportFrom)
        for each_name in each_import.names
        if each_name.name.startswith("check_")
    )
    documented_checks: Counter[str] = Counter()
    for each_family_path in _FAMILY_DIRECTORY.glob("*.md"):
        if each_family_path.name == "README.md":
            continue
        family_text = each_family_path.read_text(encoding="utf-8")
        assert re.findall(r"^## (.+)$", family_text, re.MULTILINE) == [
            "Checks",
            "When it fires",
            "Proving it",
            "Gotchas",
        ], each_family_path
        checks_match = re.search(
            r"^## Checks\s*\n(.*?)(?=^## |\Z)", family_text, re.MULTILINE | re.DOTALL
        )
        assert checks_match is not None, each_family_path
        family_checks = re.findall(
            r"^- (check_\w+)\s*$", checks_match.group(1), re.MULTILINE
        )
        proof_checks = re.findall(r"^- (check_\w+):", family_text, re.MULTILINE)
        assert Counter(proof_checks) == Counter(family_checks), each_family_path
        documented_checks.update(family_checks)
    assert documented_checks == imported_checks


def _assert_proof_target_resolves(proof_label: str, proof_target: str) -> None:
    module_text, _, test_name = proof_target.partition("::")
    module_path = _REPOSITORY_ROOT / module_text
    assert module_path.is_file(), proof_label
    if test_name:
        assert re.search(
            rf"^def {re.escape(test_name)}\(",
            module_path.read_text(encoding="utf-8"),
            re.MULTILINE,
        ), proof_label


def test_should_name_a_test_module_in_each_proof_command() -> None:
    for each_family_path in _FAMILY_DIRECTORY.glob("*.md"):
        family_text = each_family_path.read_text(encoding="utf-8")
        all_proofs = re.findall(
            r"^- (check_\w+):.*?`python -m pytest ([^`\s]+)", family_text, re.MULTILINE
        )
        for each_check, each_target in all_proofs:
            _assert_proof_target_resolves(
                f"{each_family_path.name}: {each_check} -> {each_target}", each_target
            )


def _collect_citation_texts() -> list[tuple[Path, str]]:
    all_citations: list[tuple[Path, str]] = []
    for each_root in _CITATION_ROOTS:
        all_candidate_paths = [
            each_path
            for each_path in each_root.rglob("*")
            if each_path.is_file() and each_path.suffix in _TEXT_SUFFIXES
        ]
        all_citations.extend(
            (each_path, each_path.read_text(encoding="utf-8"))
            for each_path in all_candidate_paths
        )
    return all_citations


def test_should_resolve_code_rules_anchors_and_sections() -> None:
    index_text = _INDEX_PATH.read_text(encoding="utf-8")
    _assert_citations_resolve(index_text, _collect_citation_texts())


def test_should_report_dead_code_rules_anchor() -> None:
    index_text = _INDEX_PATH.read_text(encoding="utf-8")
    dead_citation = (_INDEX_PATH, "CODE_RULES.md" + "#no-such-heading")
    with pytest.raises(AssertionError, match="dead CODE_RULES anchor #no-such-heading"):
        _assert_citations_resolve(index_text, [dead_citation])


def _assert_destination_resolves(markdown_path: Path, destination: str) -> None:
    if "://" in destination or destination.startswith("#"):
        return
    path_text, _, anchor_text = destination.partition("#")
    destination_path = markdown_path.parent / path_text
    assert destination_path.is_file(), f"{markdown_path}: {destination}"
    if anchor_text:
        destination_text = destination_path.read_text(encoding="utf-8")
        assert anchor_text in _heading_slugs(destination_text), (
            f"{markdown_path}: {destination}"
        )


def test_should_resolve_every_index_and_family_relative_link() -> None:
    for each_markdown_path in [_INDEX_PATH, *_FAMILY_DIRECTORY.glob("*.md")]:
        markdown_text = each_markdown_path.read_text(encoding="utf-8")
        for each_destination in _MARKDOWN_LINK.findall(markdown_text):
            _assert_destination_resolves(each_markdown_path, each_destination)
