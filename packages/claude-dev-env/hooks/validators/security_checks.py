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

from .config import security_checks_constants as secret_constants
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


def _bare_word(word: str) -> str | None:
    """Return a word without edge punctuation, or None for a word to report.

    A word that holds a format placeholder comes back empty when nothing but
    punctuation stands beside the placeholder, and as None when letters do.
    """
    stripped_word = word.strip(secret_constants.WORD_EDGE_PUNCTUATION)
    word_without_placeholders = secret_constants.FORMAT_PLACEHOLDER_PATTERN.sub(
        "", stripped_word
    )
    if word_without_placeholders == stripped_word:
        return stripped_word or None
    remainder = word_without_placeholders.strip(secret_constants.WORD_EDGE_PUNCTUATION)
    return None if remainder else ""


def _is_capitals_word(bare_word: str) -> bool:
    return len(bare_word) > 1 and bare_word.isupper()


def _is_plain_word(bare_word: str, is_lead_word: bool) -> bool:
    if not (bare_word.isascii() and bare_word.isalpha()):
        return False
    if _is_capitals_word(bare_word):
        return len(bare_word) <= secret_constants.MAXIMUM_CAPITALS_WORD_LENGTH
    if len(bare_word) > secret_constants.MAXIMUM_ORDINARY_WORD_LENGTH:
        return False
    if secret_constants.UNPRONOUNCEABLE_RUN_PATTERN.search(bare_word):
        return False
    return bare_word.islower() or (is_lead_word and bare_word[1:].islower())


def _has_only_plain_words(all_bare_words: list[str | None]) -> bool:
    for each_index, each_word in enumerate(all_bare_words):
        if each_word is None:
            return False
        if each_word and not _is_plain_word(each_word, is_lead_word=each_index == 0):
            return False
    all_capitals_words = [
        each_word for each_word in all_bare_words if _is_capitals_word(each_word or "")
    ]
    return len(all_capitals_words) <= secret_constants.MAXIMUM_CAPITALS_WORD_COUNT


def _has_unknown_short_word(all_lowered_words: list[str]) -> bool:
    return any(
        0 < len(each_word) <= secret_constants.MAXIMUM_SHORT_WORD_LENGTH
        and each_word not in secret_constants.ALL_SENTENCE_FUNCTION_WORDS
        for each_word in all_lowered_words
    )


def _has_label_before_value(all_words: list[str]) -> bool:
    return any(
        each_word.endswith(secret_constants.LABEL_CLOSING_MARK)
        for each_word in all_words[:-1]
    )


def _has_auth_scheme_before_value(all_lowered_words: list[str]) -> bool:
    if all_lowered_words[0] in secret_constants.ALL_AUTH_SCHEME_LEAD_WORDS:
        return True
    return any(
        each_word in secret_constants.ALL_AUTH_SCHEME_WORDS
        for each_word in all_lowered_words[:-1]
    )


def _has_equal_length_group(all_bare_words: list[str]) -> bool:
    run_length = 0
    previous_length = 0
    for each_word in all_bare_words:
        is_group_word = len(each_word) >= secret_constants.MINIMUM_GROUP_WORD_LENGTH
        run_length = (
            run_length + 1 if is_group_word and len(each_word) == previous_length else 1
        )
        previous_length = len(each_word) if is_group_word else 0
        if run_length >= secret_constants.MINIMUM_GROUP_RUN_LENGTH:
            return True
    return False


def _reads_as_message(literal_text: str) -> bool:
    """Return whether a string literal reads as a message a person wrote.

    The default verdict is "not a message". A value is a message only when
    every sign agrees: four or more words with one space between them; each
    one a short plain lowercase word, a lead word with one capital, one short
    capitals word at most, or a format placeholder that stands alone; a
    sentence function word among them; no other word of one or two letters;
    no authentication scheme word before another word; no label that ends in
    a colon before another word; and no run of three words of one length, as
    a grouped key has.

    Args:
        literal_text: The string value assigned to a sensitive name.

    Returns:
        Whether the value is prose with nothing key-shaped in it.
    """
    all_words = literal_text.split(secret_constants.WORD_SEPARATOR)
    if len(all_words) < secret_constants.MINIMUM_MESSAGE_WORD_COUNT:
        return False
    if all_words != literal_text.split():
        return False
    all_bare_words = [_bare_word(each_word) for each_word in all_words]
    if not _has_only_plain_words(all_bare_words):
        return False
    all_lowered_words = [(each_word or "").lower() for each_word in all_bare_words]
    if _has_auth_scheme_before_value(all_lowered_words):
        return False
    if _has_unknown_short_word(all_lowered_words):
        return False
    if _has_label_before_value(all_words) or _has_equal_length_group(all_lowered_words):
        return False
    return not secret_constants.ALL_SENTENCE_FUNCTION_WORDS.isdisjoint(
        all_lowered_words
    )


def _has_pointer_segments(
    pointer_text: str,
    separator: str,
    segment_pattern: re.Pattern[str],
    minimum_segment_count: int,
) -> bool:
    all_segments = pointer_text.split(separator)
    if len(all_segments) < minimum_segment_count:
        return False
    if not all(segment_pattern.fullmatch(each_segment) for each_segment in all_segments):
        return False
    lowered_text = pointer_text.lower()
    return any(
        each_word in lowered_text for each_word in secret_constants.ALL_POINTER_VALUE_WORDS
    )


def _names_the_variable_or_flag_it_points_to(
    variable_name: str, literal_text: str
) -> bool:
    """Return whether a pointer-named constant holds a variable or flag name.

    The name must end in a suffix that says the value points somewhere, and
    the value must be letters-only segments that hold a word such as token
    or key, the way the name of a variable or flag for a credential does.
    """
    if variable_name.endswith(secret_constants.ALL_VARIABLE_NAME_SUFFIXES):
        return _has_pointer_segments(
            literal_text,
            secret_constants.NAME_SEGMENT_SEPARATOR,
            secret_constants.VARIABLE_NAME_SEGMENT_PATTERN,
            secret_constants.MINIMUM_VARIABLE_SEGMENT_COUNT,
        )
    is_flag_name = variable_name.endswith(secret_constants.ALL_FLAG_NAME_SUFFIXES)
    if not (is_flag_name and literal_text.startswith(secret_constants.FLAG_LEAD)):
        return False
    return _has_pointer_segments(
        literal_text.removeprefix(secret_constants.FLAG_LEAD),
        secret_constants.FLAG_SEGMENT_SEPARATOR,
        secret_constants.FLAG_SEGMENT_PATTERN,
        secret_constants.MINIMUM_FLAG_SEGMENT_COUNT,
    )


def _is_password_name(variable_name: str) -> bool:
    if any(
        each_word in variable_name
        for each_word in secret_constants.ALL_PASSWORD_NAME_WORDS
    ):
        return True
    all_name_segments = variable_name.split(secret_constants.NAME_SEGMENT_SEPARATOR)
    return not secret_constants.ALL_PASSWORD_NAME_SEGMENTS.isdisjoint(all_name_segments)


def _is_secret_value(variable_name: str, literal_text: str) -> bool:
    if _is_secret_metadata(variable_name, literal_text):
        return False
    if _is_password_name(variable_name):
        return True
    if _names_the_variable_or_flag_it_points_to(variable_name, literal_text):
        return False
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
