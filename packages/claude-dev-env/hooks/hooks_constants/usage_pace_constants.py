"""Constants for the usage-pace reader that the thread spawn pace hook runs.

Groups: the OAuth usage endpoint probe, the token and certificate sources,
the rate windows and their lengths, the exit codes, and the JSON keys of the
verdict.
"""

from __future__ import annotations

from datetime import timedelta

USAGE_ENDPOINT_URL = "https://api.anthropic.com/api/oauth/usage"
ANTHROPIC_BETA_HEADER = "anthropic-beta"
USAGE_BETA_VALUE = "oauth-2025-04-20"
AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "
CONTENT_TYPE_HEADER_NAME = "Content-Type"
CONTENT_TYPE_JSON = "application/json"
PROBE_TIMEOUT_SECONDS = 8

INGRESS_BEARER_FILE_ENV_VAR = "CLAUDE_SESSION_INGRESS_TOKEN_FILE"
SSL_CERT_FILE_ENV_VAR = "SSL_CERT_FILE"
CONTAINER_PROXY_CA_BUNDLE_PATH = "/root/.ccr/ca-bundle.crt"

UTILIZATION_KEY = "utilization"
RESETS_AT_KEY = "resets_at"
ISO_UTC_SUFFIX = "Z"
ISO_UTC_OFFSET = "+00:00"
ALL_RATE_WINDOW_LENGTHS = (
    ("five_hour", timedelta(hours=5)),
    ("seven_day", timedelta(days=7)),
)
PERCENT_SCALE = 100.0
PERCENT_DECIMAL_PLACES = 1
MINIMUM_ELAPSED_PERCENT_FOR_PACE = 10.0

EXIT_CODE_OVER_PACE = 0
EXIT_CODE_UNDER_PACE = 1
EXIT_CODE_UNREADABLE = 2

RESULT_KEY_OVER_PACE = "over_pace"
RESULT_KEY_CHECKED_AT = "checked_at"
RESULT_KEY_WINDOWS = "windows"
RESULT_KEY_ERROR = "error"
WINDOW_KEY_NAME = "window"
WINDOW_KEY_USED_PERCENT = "used_percent"
WINDOW_KEY_ELAPSED_PERCENT = "elapsed_percent"
WINDOW_KEY_RESETS_AT = "resets_at"
WINDOW_KEY_OVER_PACE = "over_pace"
