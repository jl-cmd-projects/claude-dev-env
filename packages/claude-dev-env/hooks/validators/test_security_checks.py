"""Tests for security vulnerability detection."""

import ast

import pytest

from .security_checks import (
    check_hardcoded_secrets,
    check_sql_injection,
    check_xss_risk,
)
from .validator_base import Violation


GOOD_NO_SECRETS = '''
import os

def get_api_key():
    return os.environ.get("API_KEY")
'''

BAD_HARDCODED_API_KEY = '''
API_KEY = "sk-abc123xyz789"
'''

BAD_HARDCODED_PASSWORD = '''
def connect():
    password = "super_secret_123"
    return password
'''

METADATA_SOURCE_FIXTURE = '''
AUTHORIZATION_HEADER = "Authorization"
TOKEN_KEY = "token"
INSTALLATION_TOKEN_ENDPOINT_TEMPLATE = "/app/installations/{installation_id}/access_tokens"
TOKEN_RESOURCE_NAME = "installation token"
'''

HEADER_SOURCE_FIXTURE = '''
AUTHORIZATION_HEADER = "actualsecret"
'''

ERROR_SOURCE_FIXTURE = '''
PASSWORD_ERROR = "my secret password"
'''

UNSAFE_KEY_METADATA_SOURCE_FIXTURES = (
    '''
secret_key = "secret"
''',
    '''
password_key = "password"
''',
)

ALL_CLEARED_NAME_VALUE_PAIRS = (
    ("FAIL_NO_TOKENS", "No tokens were found in the response."),
    ("FAIL_NO_TOKENS", "no tokens were found in the response"),
    ("SECRET_MISSING_MESSAGE", "Set the secret in the environment before the run."),
    ("AUTH_FAILURE_TEMPLATE", "Sign in failed for {account_name}, try again"),
    ("AUTH_FAILURE_TEMPLATE", "The call for {account_name!r} took {elapsed:.2f} seconds"),
    ("token_hint", "paste a token below"),
    ("TOKEN_MESSAGE", "The HTTP call was refused by the server."),
    ("SERVICE_TOKEN_ENV", "SERVICE_API_TOKEN"),
    ("SERVICE_AUTH_ENV_VAR", "MAX_TOKENS"),
    ("MAXIMUM_TOKENS_FLAG", "--max-tokens"),
    ("TOKEN_OPTION", "--token"),
)

ALL_AUTH_HEADER_NAME_VALUE_PAIRS = (
    ("AUTH_HEADER_VALUE", "Bearer abcdefghijklmnopqrstuvwxyz"),
    ("AUTH_HEADER_VALUE", "Bearer xyz"),
    ("AUTH_HEADER_VALUE", "Token abcdefghijklmnop"),
    ("AUTH_HEADER_VALUE", "Bearer is the word"),
    ("AUTH_VALUE", "Authorization is Bearer abcdefghijklmn"),
    ("AUTH_VALUE", "the Bearer abcdefghijklmn"),
    ("AUTH_VALUE", "a Basic dxnlcjpwyxnz"),
    ("AUTH_VALUE", "send the basic word in the call"),
)

ALL_WRAPPED_KEY_NAME_VALUE_PAIRS = (
    ("FAIL_NO_TOKENS", "aaaa1111bbbb"),
    ("SERVICE_API_KEY", "Use zq_live_abcdefghijklmnopqrstuvwx here"),
    ("SERVICE_API_KEY", "Key zq-live-abcdefghijklmnop."),
    ("SERVICE_TOKEN", "Use AbCdEfGhIjKlMnOpQrStUvWx for the call"),
    ("SERVICE_SECRET", "Key wJalrXUtnFEMI/KzMDENG/bPxRfiCYEXAMPLEKEY"),
    ("SERVICE_TOKEN", "zqzq-abcdefghij-klmnopqrst is the one."),
    ("SERVICE_TOKEN", "{prefix} AbCdEfGhIjKlMnOp"),
    ("SERVICE_TOKEN", "Token:\tabcdefghijklmnopqrstuvwxyzabcdef"),
    ("SERVICE_TOKEN", "Send the abcdefghijklmnopqrstuvwxyz with each call."),
    ("SERVICE_TOKEN", "{zq-live-abcdefghijklmnop} is the key for it"),
    ("SERVICE_TOKEN", "the token for it is {AbCdEf123456GhIjKl}"),
    ("SERVICE_TOKEN", "the token for it is {hunter2}"),
    ("SERVICE_TOKEN", "the key for it is zq{live}abc"),
    ("SERVICE_TOKEN", "the key for it is {}hunter"),
    ("SERVICE_TOKEN", "the key for it is {name:swordfish}"),
    ("SERVICE_TOKEN", "use qwxzjkvbnmplrt for the call"),
    ("SERVICE_TOKEN", "Send the abcdefghijklmn with each call."),
    ("SERVICE_TOKEN", "the key is\nswordfish in the pond"),
    ("SERVICE_TOKEN", "the key is  swordfish in the pond"),
    ("SERVICE_TOKEN", "the key is \u0661\u0662\u0663 in the pond"),
    ("SERVICE_TOKEN", "the key is hunt\u0435r in the pond"),
    ("SERVICE_SECRET", "::: is the !!! in it"),
    ("SERVICE_SECRET", "the token is 'swordfish' for it"),
    ("SERVICE_SECRET", "the token is: swordfish in the pond"),
    ("SERVICE_SECRET", "login: admin swordfish for the store"),
    ("SERVICE_SECRET", "it is Swordfish in the pond"),
    ("AUTH_HINT", "Open the page with ?access_token=abcdef to sign in."),
    ("AUTH_NOTE", "The store is at https://admin:hunterpass@example.test/db."),
)

ALL_VARIABLE_OR_FLAG_SHAPED_NAME_VALUE_PAIRS = (
    ("DB_PASSWORD", "PROD_DB_PASS"),
    ("DB_PASSWORD", "HUNTER_TWO"),
    ("DB_PASSWORD", "--swordfish"),
    ("DB_PASSWORD", "--open-sesame"),
    ("SERVICE_SECRET", "PROD_SERVICE_PASS"),
    ("SERVICE_TOKEN_ENV", "--swordfish"),
    ("SERVICE_TOKEN_FLAG", "PROD_SERVICE_PASS"),
    ("SERVICE_TOKEN_ENV", "prod_service_pass"),
    ("SERVICE_AUTH_ENV", "AKIAIOSFODNNEXAMPLE"),
    ("SERVICE_AUTH_ENV", "HUNTER_TWO"),
    ("SERVICE_AUTH_ENV", "TOKEN_X9K2"),
    ("SERVICE_SECRET_ENV_NAME", "XKLQZPMTVTOKENXKLQZPMTV"),
    ("DB_PASSWORD_ENV", "DB_PASSWORD"),
    ("DB_PASSWORD_FLAG", "--open-sesame"),
    ("SECRET_OPTION", "--swordfish"),
    ("SECRET_OPTION", "--token9"),
)

ALL_PASSPHRASE_NAME_VALUE_PAIRS = (
    ("SERVICE_TOKEN", "Correct horse battery staple"),
    ("SECRET_PHRASE", "correct horse battery staple."),
    ("PASSWORD", "Open Sesame"),
    ("PASSWORD", "Admin admin"),
    ("PASSWORD", "P@ssword One!"),
    ("DB_PASSWORD", "Password: swordfish"),
    ("SERVICE_SECRET", "Password: swordfish"),
    ("SERVICE_SECRET", "The secret: swordfish in the pond"),
    ("PASSWORD", "The password is swordfish."),
    ("PASSWORD_ERROR", "My secret password"),
    ("PASSWORD_HINT", "It was the best of times."),
    ("SECRET_PASSPHRASE", "it was the best of times"),
    ("SECRET_PHRASE", "it was the best of times"),
    ("SECRET_ANSWER", "the name of the first dog"),
    ("SECRET_PASS", "it is in the pond"),
    ("AUTH_PASS", "open the pod bay doors"),
    ("AUTH_PASSCODE", "it is in the pond"),
    ("SERVICE_TOKEN", "swordfish is it"),
    ("SERVICE_API_KEY", "the key is zq live abc"),
    ("SERVICE_TOKEN", "my voice is my passport"),
    ("SERVICE_TOKEN", "the Secret swordfish"),
)

ALL_GROUPED_KEY_NAME_VALUE_PAIRS = (
    ("SECRET_KEY", "QUJD REVG R0hJ SktM"),
    ("APP_PASSWORD", "Abcd efgh ijkl mnop"),
    ("SERVICE_SECRET", "Abcd efgh ijkl mnop"),
    ("SERVICE_SECRET", "that with from this"),
    ("SERVICE_SECRET", "that with from this."),
    ("SERVICE_SECRET", "abcd efgh ijkl with."),
    ("SERVICE_SECRET", "wxyz on abcd efgh ijkl"),
    ("SERVICE_SECRET", "the AKIA IOSFO DNNEX AMPLE"),
    ("SERVICE_SECRET", "QUJD REVG ROHJ SKTM a"),
    ("SERVICE_SECRET", "AKIA is the ABCDE"),
    ("SERVICE_SECRET", "a 123 456 789 012"),
    ("SERVICE_TOKEN", "the code is 123 456"),
    ("SERVICE_TOKEN", "the code is 123"),
    ("DB_AUTH_URL", "Host db.example.test user admin pass swordfish"),
)

ALL_REPORTED_NAME_VALUE_PAIRS = (
    *ALL_AUTH_HEADER_NAME_VALUE_PAIRS,
    *ALL_WRAPPED_KEY_NAME_VALUE_PAIRS,
    *ALL_VARIABLE_OR_FLAG_SHAPED_NAME_VALUE_PAIRS,
    *ALL_PASSPHRASE_NAME_VALUE_PAIRS,
    *ALL_GROUPED_KEY_NAME_VALUE_PAIRS,
)


def _assignment_tree(variable_name: str, literal_text: str) -> ast.AST:
    return ast.parse(f"{variable_name} = {literal_text!r}")


GOOD_PARAMETERIZED_SQL = '''
def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
'''

BAD_FSTRING_SQL = '''
def get_user(user_id):
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
'''

BAD_FORMAT_SQL = '''
def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE id = {}".format(user_id))
'''

GOOD_ESCAPED_HTML = '''
from django.utils.html import escape

def render(user_input):
    return escape(user_input)
'''

BAD_MARK_SAFE = '''
from django.utils.safestring import mark_safe

def render(user_input):
    return mark_safe(user_input)
'''


class TestHardcodedSecrets:
    def test_env_variable_passes(self) -> None:
        tree = ast.parse(GOOD_NO_SECRETS)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert violations == []

    def test_hardcoded_api_key_fails(self) -> None:
        tree = ast.parse(BAD_HARDCODED_API_KEY)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert len(violations) == 1
        assert "API_KEY" in violations[0].message or "secret" in violations[0].message.lower()

    def test_hardcoded_password_fails(self) -> None:
        tree = ast.parse(BAD_HARDCODED_PASSWORD)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert len(violations) == 1

    def test_secret_metadata_passes(self) -> None:
        tree = ast.parse(METADATA_SOURCE_FIXTURE)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert violations == []

    def test_authorization_header_value_fails(self) -> None:
        tree = ast.parse(HEADER_SOURCE_FIXTURE)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert len(violations) == 1

    def test_password_error_fails(self) -> None:
        tree = ast.parse(ERROR_SOURCE_FIXTURE)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert len(violations) == 1

    @pytest.mark.parametrize("source_fixture", UNSAFE_KEY_METADATA_SOURCE_FIXTURES)
    def test_sensitive_key_values_fail(self, source_fixture: str) -> None:
        tree = ast.parse(source_fixture)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert len(violations) == 1

    @pytest.mark.parametrize(
        "endpoint",
        (
            "/tokens/{token_id}?access_token=actualsecret",
            "/tokens/{token_id}#actualsecret",
        ),
    )
    def test_token_endpoint_credentials_fail(self, endpoint: str) -> None:
        tree = ast.parse(f'TOKEN_ENDPOINT_TEMPLATE = "{endpoint}"')
        violations = check_hardcoded_secrets(tree, "test.py")
        assert len(violations) == 1

    @pytest.mark.parametrize(
        ("variable_name", "literal_text"), ALL_CLEARED_NAME_VALUE_PAIRS
    )
    def test_message_or_pointer_value_under_sensitive_name_passes(
        self, variable_name: str, literal_text: str
    ) -> None:
        tree = _assignment_tree(variable_name, literal_text)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert violations == []

    @pytest.mark.parametrize(
        ("variable_name", "literal_text"), ALL_REPORTED_NAME_VALUE_PAIRS
    )
    def test_secret_shaped_value_fails(
        self, variable_name: str, literal_text: str
    ) -> None:
        tree = _assignment_tree(variable_name, literal_text)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert len(violations) == 1


class TestSqlInjection:
    def test_parameterized_query_passes(self) -> None:
        violations = check_sql_injection(GOOD_PARAMETERIZED_SQL, "test.py")
        assert violations == []

    def test_fstring_sql_fails(self) -> None:
        violations = check_sql_injection(BAD_FSTRING_SQL, "test.py")
        assert len(violations) == 1
        assert "SQL" in violations[0].message or "injection" in violations[0].message.lower()

    def test_format_sql_fails(self) -> None:
        violations = check_sql_injection(BAD_FORMAT_SQL, "test.py")
        assert len(violations) == 1


class TestXssRisk:
    def test_escaped_html_passes(self) -> None:
        tree = ast.parse(GOOD_ESCAPED_HTML)
        violations = check_xss_risk(tree, "test.py")
        assert violations == []

    def test_mark_safe_fails(self) -> None:
        tree = ast.parse(BAD_MARK_SAFE)
        violations = check_xss_risk(tree, "test.py")
        assert len(violations) == 1
        assert "mark_safe" in violations[0].message or "XSS" in violations[0].message
