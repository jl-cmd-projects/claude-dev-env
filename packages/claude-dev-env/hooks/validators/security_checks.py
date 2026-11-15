"""Security vulnerability detection validator.

Implements:
- Check 27: Hardcoded secrets (API keys, passwords, tokens)
- Check 28: SQL injection risk (f-strings/format in SQL)
- Check 29: XSS risk (mark_safe without sanitization)
"""

import ast
import re
import sys
from pathlib import Path
from typing import List

from .config.security_checks_constants import (
    ALL_AUTH_SCHEME_LEAD_WORDS,
    ALL_FLAG_NAME_SUFFIXES,
    ALL_PASSWORD_NAME_WORDS,
    ALL_SENSITIVE_LABEL_WORDS,
    ALL_SENTENCE_FUNCTION_WORDS,
    ALL_VARIABLE_NAME_SUFFIXES,
    FLAG_VALUE_PATTERN,
    FORMAT_PLACEHOLDER_PATTERN,
    LABEL_CLOSING_MARK,
    MAXIMUM_CAPITALS_WORD_LENGTH,
    MAXIMUM_NUMBER_WORD_LENGTH,
    MAXIMUM_ORDINARY_WORD_LENGTH,
    MINIMUM_MESSAGE_WORD_COUNT,
    VARIABLE_NAME_VALUE_PATTERN,
    WORD_EDGE_PUNCTUATION,
)
from .validator_base import Violation, source_text, syntax_tree


SECRET_PATTERNS: frozenset[str] = frozenset({
    "api_key", "apikey", "api-key",
    "password", "passwd", "pwd",
    "secret", "token", "auth",
    "private_key", "privatekey",
    "credential", "credentials",
})

SQL_EXECUTE_PATTERN = re.compile(r"\.execute\s*\(\s*f['\"]|\.execute\s*\([^)]*\.format\(", re.IGNORECASE)


def _normalize_metadata_name(metadata_text: str) -> str:
    return "".join(
        each_character for each_character in metadata_text.lower() if each_character.isalnum()
    )


def _is_schema_key_metadata(variable_name: str, literal_text: str) -> bool:
    return variable_name == "token_key" and _normalize_metadata_name(literal_text) == "token"


def _is_header_metadata(variable_name: str, literal_text: str) -> bool:
    if not variable_name.endswith("_header"):
        return False
    header_name = variable_name.removesuffix("_header")
    return _normalize_metadata_name(literal_text) == _normalize_metadata_name(header_name)


def _is_endpoint_template_metadata(variable_name: str, literal_text: str) -> bool:
    if not variable_name.endswith("_endpoint_template"):
        return False
    endpoint_template_pattern = re.compile(r"^/[A-Za-z0-9_{}./-]+$")
    if endpoint_template_pattern.fullmatch(literal_text) is None or "{" not in literal_text:
        return False
    endpoint_name = variable_name.removesuffix("_endpoint_template")
    normalized_endpoint = _normalize_metadata_name(literal_text)
    return all(each_word in normalized_endpoint for each_word in endpoint_name.split("_"))


def _is_resource_name_metadata(variable_name: str, literal_text: str) -> bool:
    if not variable_name.endswith("_resource_name"):
        return False
    all_label_words = literal_text.lower().split()
    resource_name = variable_name.removesuffix("_resource_name")
    return (
        len(all_label_words) > 1
        and all(each_word.isalpha() for each_word in all_label_words)
        and _normalize_metadata_name(all_label_words[-1]) == _normalize_metadata_name(resource_name)
    )


def _is_secret_metadata(variable_name: str, literal_text: str) -> bool:
    if _is_schema_key_metadata(variable_name, literal_text):
        return True
    if _is_header_metadata(variable_name, literal_text):
        return True
    if _is_endpoint_template_metadata(variable_name, literal_text):
        return True
    return _is_resource_name_metadata(variable_name, literal_text)


def _bare_word(word: str) -> str:
    word_without_placeholders = FORMAT_PLACEHOLDER_PATTERN.sub("", word)
    return word_without_placeholders.strip(WORD_EDGE_PUNCTUATION)


def _is_ordinary_word(bare_word: str) -> bool:
    if not bare_word:
        return True
    if bare_word.isdigit():
        return len(bare_word) <= MAXIMUM_NUMBER_WORD_LENGTH
    if not (bare_word.isascii() and bare_word.isalpha()):
        return False
    if bare_word.isupper():
        return len(bare_word) <= MAXIMUM_CAPITALS_WORD_LENGTH
    if len(bare_word) > MAXIMUM_ORDINARY_WORD_LENGTH:
        return False
    return bare_word[1:].islower() or len(bare_word) == 1


def _has_label_before_value(all_words: list[str]) -> bool:
    for each_index, each_word in enumerate(all_words[:-1]):
        if not each_word.endswith(LABEL_CLOSING_MARK):
            continue
        has_one_word_after = len(all_words[each_index + 1 :]) == 1
        if has_one_word_after or _bare_word(each_word).lower() in ALL_SENSITIVE_LABEL_WORDS:
            return True
    return False


def _reads_as_message(literal_text: str) -> bool:
    """Return whether a string literal reads as a message a person wrote.

    The default verdict is "not a message". A value is a message only when
    every sign agrees: three or more words, each one a short plain word, a
    short number or a format placeholder; a sentence function word among them;
    no authentication scheme word in the lead; no label with a value after
    it; and words that differ in length, unlike a grouped key.

    Args:
        literal_text: The string value assigned to a sensitive name.

    Returns:
        Whether the value is prose with nothing key-shaped in it.
    """
    all_words = literal_text.split()
    if len(all_words) < MINIMUM_MESSAGE_WORD_COUNT:
        return False
    all_bare_words = [_bare_word(each_word) for each_word in all_words]
    if not all(_is_ordinary_word(each_word) for each_word in all_bare_words):
        return False
    all_lowered_words = [each_word.lower() for each_word in all_bare_words]
    if all_lowered_words[0] in ALL_AUTH_SCHEME_LEAD_WORDS:
        return False
    if _has_label_before_value(all_words):
        return False
    if len({len(each_word) for each_word in all_words}) == 1:
        return False
    return not ALL_SENTENCE_FUNCTION_WORDS.isdisjoint(all_lowered_words)


def _names_the_variable_or_flag_it_points_to(
    variable_name: str, literal_text: str
) -> bool:
    if variable_name.endswith(ALL_VARIABLE_NAME_SUFFIXES):
        return VARIABLE_NAME_VALUE_PATTERN.fullmatch(literal_text) is not None
    if variable_name.endswith(ALL_FLAG_NAME_SUFFIXES):
        return FLAG_VALUE_PATTERN.fullmatch(literal_text) is not None
    return False


def _is_secret_value(variable_name: str, literal_text: str) -> bool:
    if _is_secret_metadata(variable_name, literal_text):
        return False
    if _names_the_variable_or_flag_it_points_to(variable_name, literal_text):
        return False
    if any(each_word in variable_name for each_word in ALL_PASSWORD_NAME_WORDS):
        return True
    return not _reads_as_message(literal_text)


def check_hardcoded_secrets(tree: ast.AST, filename: str) -> List[Violation]:
    MINIMUM_SECRET_LENGTH = 3
    violations: List[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id.lower()
                    if any(pattern in var_name for pattern in SECRET_PATTERNS):
                        if isinstance(node.value, ast.Constant) and isinstance(
                            node.value.value, str
                        ):
                            if len(node.value.value) > MINIMUM_SECRET_LENGTH and _is_secret_value(
                                var_name, node.value.value
                            ):
                                violations.append(
                                    Violation(
                                        filename,
                                        node.lineno,
                                        f"Hardcoded secret in '{target.id}' - use environment variable",
                                    )
                                )

    return violations


def check_sql_injection(source: str, filename: str) -> List[Violation]:
    violations: List[Violation] = []
    lines = source.splitlines()

    for line_num, line in enumerate(lines, start=1):
        if SQL_EXECUTE_PATTERN.search(line):
            violations.append(
                Violation(
                    filename,
                    line_num,
                    "SQL injection risk - use parameterized queries instead of f-string/format",
                )
            )

    return violations


def check_xss_risk(tree: ast.AST, filename: str) -> List[Violation]:
    violations: List[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "mark_safe":
                violations.append(
                    Violation(
                        filename,
                        node.lineno,
                        "XSS risk - mark_safe() on user input is dangerous",
                    )
                )
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "mark_safe":
                violations.append(
                    Violation(
                        filename,
                        node.lineno,
                        "XSS risk - mark_safe() on user input is dangerous",
                    )
                )

    return violations


def validate_file(file_path: Path) -> List[Violation]:
    violations: List[Violation] = []
    filename = str(file_path)

    try:
        source = source_text(file_path)
    except Exception as error:
        return [Violation(filename, 0, f"Error reading file: {error}")]

    try:
        tree = syntax_tree(source)
    except SyntaxError as error:
        return [Violation(filename, error.lineno or 0, f"Syntax error: {error.msg}")]

    violations.extend(check_hardcoded_secrets(tree, filename))
    violations.extend(check_sql_injection(source, filename))
    violations.extend(check_xss_risk(tree, filename))

    return violations


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: security_checks.py <file1.py> [file2.py ...]", file=sys.stderr)
        return 1

    all_violations: List[Violation] = []

    for file_arg in sys.argv[1:]:
        file_path = Path(file_arg)
        if not file_path.exists():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            return 1
        all_violations.extend(validate_file(file_path))

    for violation in all_violations:
        print(violation)

    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
