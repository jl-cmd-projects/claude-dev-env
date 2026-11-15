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

MESSAGE_VALUE_SOURCE_FIXTURES = (
    'FAIL_NO_TOKENS = "No tokens were found in the response."',
    'SECRET_MISSING_MESSAGE = "Set the secret in the environment before the run."',
    'AUTH_FAILURE_TEMPLATE = "Sign-in failed for {account_name}: try again"',
    'AUTHOR_LABEL = "Written By"',
    'token_hint = "Paste a token below"',
    'TOKEN_SETUP_MESSAGE = "Set SERVICE_API_TOKEN before the run."',
    'TOKEN_VARIABLE_NAME = "SERVICE_API_TOKEN"',
    'MAXIMUM_TOKENS_FLAG = "--max-tokens"',
)

SECRET_VALUE_UNDER_MESSAGE_NAME_SOURCE_FIXTURES = (
    'FAIL_NO_TOKENS = "sk-abc123xyz789"',
    'TOKEN_MESSAGE = "Send the token ghp_0123456789abcdefABCDEF with each call."',
    'AUTH_HINT = "Open the page with ?access_token=abcdef to sign in."',
    'SECRET_PHRASE = "correct horse battery staple"',
    'TOKEN_MESSAGE = "Token: ABCDEFGHIJKLMNOP"',
    'TOKEN_MESSAGE = "{prefix} deadbeefcafebabe"',
    'PASSWORD_MESSAGE = "The store is https://admin:hunterpass@example.test/db."',
    'TOKEN_VARIABLE_NAME = "SERVICE_API_TOKEN_0a1b2c3d"',
    'AUTH_FAILURE_TEMPLATE = "Sign-in failed for {account_name} with hunter2hunter2"',
)

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

    @pytest.mark.parametrize("source_fixture", MESSAGE_VALUE_SOURCE_FIXTURES)
    def test_message_value_under_sensitive_name_passes(
        self, source_fixture: str
    ) -> None:
        tree = ast.parse(source_fixture)
        violations = check_hardcoded_secrets(tree, "test.py")
        assert violations == []

    @pytest.mark.parametrize(
        "source_fixture", SECRET_VALUE_UNDER_MESSAGE_NAME_SOURCE_FIXTURES
    )
    def test_secret_value_under_message_name_fails(self, source_fixture: str) -> None:
        tree = ast.parse(source_fixture)
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
