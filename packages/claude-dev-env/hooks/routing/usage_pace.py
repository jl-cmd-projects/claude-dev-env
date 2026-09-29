#!/usr/bin/env python3
"""Report whether the account running the project spends faster than its windows reset.

::

    python usage_pace.py
    {"over_pace": true, "checked_at": "2026-09-29T13:57:40+00:00",
     "windows": [{"window": "five_hour", "used_percent": 3.0,
                  "elapsed_percent": 2.6, "resets_at": "...", "over_pace": true},
                 {"window": "seven_day", "used_percent": 93.0,
                  "elapsed_percent": 39.3, "resets_at": "...", "over_pace": true}]}

A window is over pace when its used percent exceeds the percent of the window
already elapsed. The account is over pace when any window is. The script reads
the OAuth usage endpoint with the session ingress bearer token, the same probe
the usage-pause skill's ``resolve_usage_window.py`` uses. It never prints or
stores the token.

Exit codes: 0 over pace, 1 under pace, 2 unreadable. ``--payload-file`` and
``--now`` replace the live probe and the clock for a deterministic run.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.usage_pace_constants import (
    ALL_RATE_WINDOW_LENGTHS,
    ANTHROPIC_BETA_HEADER,
    AUTHORIZATION_HEADER,
    BEARER_PREFIX,
    CONTAINER_PROXY_CA_BUNDLE_PATH,
    CONTENT_TYPE_HEADER_NAME,
    CONTENT_TYPE_JSON,
    EXIT_CODE_OVER_PACE,
    EXIT_CODE_UNDER_PACE,
    EXIT_CODE_UNREADABLE,
    INGRESS_BEARER_FILE_ENV_VAR,
    ISO_UTC_OFFSET,
    ISO_UTC_SUFFIX,
    PERCENT_DECIMAL_PLACES,
    PERCENT_SCALE,
    PROBE_TIMEOUT_SECONDS,
    RESETS_AT_KEY,
    RESULT_KEY_CHECKED_AT,
    RESULT_KEY_ERROR,
    RESULT_KEY_OVER_PACE,
    RESULT_KEY_WINDOWS,
    SSL_CERT_FILE_ENV_VAR,
    USAGE_BETA_VALUE,
    USAGE_ENDPOINT_URL,
    UTILIZATION_KEY,
    WINDOW_KEY_ELAPSED_PERCENT,
    WINDOW_KEY_NAME,
    WINDOW_KEY_OVER_PACE,
    WINDOW_KEY_RESETS_AT,
    WINDOW_KEY_USED_PERCENT,
)


class UsageUnreadable(Exception):
    """The usage meters could not be read, so the pace is unknown."""


@dataclass(frozen=True)
class WindowPace:
    """One rate window's spend against the time it has run.

    Attributes:
        name: The usage bucket key, such as ``five_hour``.
        used_percent: Percent of the window's allowance spent.
        elapsed_percent: Percent of the window's length already passed.
        resets_at: When the window resets.
    """

    name: str
    used_percent: float
    elapsed_percent: float
    resets_at: datetime

    @property
    def over_pace(self) -> bool:
        """True when spend runs ahead of the clock in this window."""
        return self.used_percent > self.elapsed_percent


def _parse_resets_at(raw_resets_at: object, window_name: str) -> datetime:
    if not isinstance(raw_resets_at, str):
        raise UsageUnreadable(f"{window_name} has no resets_at time")
    try:
        parsed = datetime.fromisoformat(raw_resets_at.replace(ISO_UTC_SUFFIX, ISO_UTC_OFFSET))
    except ValueError as parse_error:
        raise UsageUnreadable(f"{window_name} resets_at is unreadable") from parse_error
    if parsed.tzinfo is None:
        raise UsageUnreadable(f"{window_name} resets_at carries no time zone")
    return parsed


def _read_utilization(all_bucket_fields: dict[object, object], window_name: str) -> float:
    raw_utilization = all_bucket_fields.get(UTILIZATION_KEY)
    if isinstance(raw_utilization, bool) or not isinstance(raw_utilization, (int, float)):
        raise UsageUnreadable(f"{window_name} has no utilization number")
    return float(raw_utilization)


def _elapsed_percent(window_length: timedelta, resets_at: datetime, now: datetime) -> float:
    elapsed_fraction = (now - (resets_at - window_length)) / window_length
    clamped_elapsed_fraction = min(max(elapsed_fraction, 0.0), 1.0)
    return round(clamped_elapsed_fraction * PERCENT_SCALE, PERCENT_DECIMAL_PLACES)


def measure_window_pace(
    window_name: str, window_length: timedelta, bucket: object, now: datetime
) -> WindowPace:
    """Measure one usage bucket's spend against its elapsed time.

    ::

        five_hour, 5h, {"utilization": 3.0, "resets_at": 18:50Z}, now 13:58Z
        -> WindowPace("five_hour", 3.0, 2.7, 18:50Z)   over pace

    Elapsed time counts from one window length before the reset, clamped to 0-100.

    Args:
        window_name: The usage bucket key.
        window_length: How long the window runs.
        bucket: The bucket object from the usage response.
        now: The time the pace is measured at.

    Raises:
        UsageUnreadable: The bucket, its utilization, or its reset is unreadable.
    """
    if not isinstance(bucket, dict):
        raise UsageUnreadable(f"usage response has no {window_name} window")
    resets_at = _parse_resets_at(bucket.get(RESETS_AT_KEY), window_name)
    return WindowPace(
        name=window_name,
        used_percent=_read_utilization(bucket, window_name),
        elapsed_percent=_elapsed_percent(window_length, resets_at, now),
        resets_at=resets_at,
    )


def measure_account_pace(
    all_usage_buckets: dict[str, object], now: datetime
) -> list[WindowPace]:
    """Measure every rate window the verdict covers.

    Args:
        all_usage_buckets: The decoded usage response body.
        now: The time the pace is measured at.

    Returns:
        One WindowPace per rate window, five-hour first.

    Raises:
        UsageUnreadable: Any covered window is missing or unreadable.
    """
    return [
        measure_window_pace(each_name, each_length, all_usage_buckets.get(each_name), now)
        for each_name, each_length in ALL_RATE_WINDOW_LENGTHS
    ]


def build_verdict(
    all_window_paces: list[WindowPace], now: datetime
) -> dict[str, object]:
    """Assemble the JSON verdict for a set of measured windows.

    Args:
        all_window_paces: The measured windows.
        now: The time the pace was measured at.

    Returns:
        The verdict mapping: the account-level flag, the check time, and
        each window's percents, reset time, and flag.
    """
    return {
        RESULT_KEY_OVER_PACE: any(
            each_pace.over_pace for each_pace in all_window_paces
        ),
        RESULT_KEY_CHECKED_AT: now.isoformat(),
        RESULT_KEY_WINDOWS: [
            {
                WINDOW_KEY_NAME: each_pace.name,
                WINDOW_KEY_USED_PERCENT: each_pace.used_percent,
                WINDOW_KEY_ELAPSED_PERCENT: each_pace.elapsed_percent,
                WINDOW_KEY_RESETS_AT: each_pace.resets_at.isoformat(),
                WINDOW_KEY_OVER_PACE: each_pace.over_pace,
            }
            for each_pace in all_window_paces
        ],
    }


def _read_session_ingress_bearer() -> str:
    configured_path = os.environ.get(INGRESS_BEARER_FILE_ENV_VAR)
    if not configured_path:
        raise UsageUnreadable(f"{INGRESS_BEARER_FILE_ENV_VAR} is unset")
    try:
        file_text = Path(configured_path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as read_error:
        raise UsageUnreadable("session ingress token file is unreadable") from read_error
    if not file_text:
        raise UsageUnreadable("session ingress token file is empty")
    return file_text


def _certificate_context() -> ssl.SSLContext:
    named_bundle = os.environ.get(SSL_CERT_FILE_ENV_VAR)
    if named_bundle:
        return ssl.create_default_context(cafile=named_bundle)
    if Path(CONTAINER_PROXY_CA_BUNDLE_PATH).is_file():
        return ssl.create_default_context(cafile=CONTAINER_PROXY_CA_BUNDLE_PATH)
    return ssl.create_default_context()


def _build_usage_request() -> urllib.request.Request:
    return urllib.request.Request(
        USAGE_ENDPOINT_URL,
        headers={
            AUTHORIZATION_HEADER: f"{BEARER_PREFIX}{_read_session_ingress_bearer()}",
            ANTHROPIC_BETA_HEADER: USAGE_BETA_VALUE,
            CONTENT_TYPE_HEADER_NAME: CONTENT_TYPE_JSON,
        },
    )


def fetch_usage_payload() -> dict[str, object]:
    """Read the usage of the account the session ingress token belongs to.

    Returns:
        The decoded response body.

    Raises:
        UsageUnreadable: No token, a failed request, or a body that is not a
            JSON object. The message names the failure type, never the token.
    """
    try:
        with urllib.request.urlopen(
            _build_usage_request(),
            timeout=PROBE_TIMEOUT_SECONDS,
            context=_certificate_context(),
        ) as usage_reply:
            decoded = json.loads(usage_reply.read())
    except urllib.error.HTTPError as http_error:
        raise UsageUnreadable(f"usage endpoint answered HTTP {http_error.code}") from http_error
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as probe_error:
        raise UsageUnreadable(
            f"usage probe failed with {type(probe_error).__name__}"
        ) from probe_error
    if not isinstance(decoded, dict):
        raise UsageUnreadable("usage response body is not a JSON object")
    return decoded


def _read_payload_file(payload_path: str) -> dict[str, object]:
    try:
        decoded = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as read_error:
        raise UsageUnreadable(
            f"payload file unreadable: {type(read_error).__name__}"
        ) from read_error
    if not isinstance(decoded, dict):
        raise UsageUnreadable("payload file is not a JSON object")
    return decoded


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report whether the account running the project spends faster than its windows reset.",
    )
    parser.add_argument(
        "--payload-file",
        default=None,
        help="A saved usage response to read instead of probing the endpoint.",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="ISO-8601 time with a zone to measure at; defaults to the current time.",
    )
    return parser.parse_args()


def _measure_verdict(arguments: argparse.Namespace) -> dict[str, object]:
    now = datetime.fromisoformat(arguments.now) if arguments.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise UsageUnreadable("--now carries no time zone")
    all_usage_buckets = (
        _read_payload_file(arguments.payload_file)
        if arguments.payload_file
        else fetch_usage_payload()
    )
    return build_verdict(measure_account_pace(all_usage_buckets, now), now)


def _write_json_line(all_document_fields: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(all_document_fields) + "\n")
    sys.stdout.flush()


def main() -> int:
    """Print the pace verdict JSON and return its exit code.

    Returns:
        0 when any window is over pace, 1 when every window is under pace,
        2 when the meters or the arguments are unreadable.
    """
    try:
        verdict = _measure_verdict(_parse_arguments())
    except (UsageUnreadable, ValueError) as unreadable:
        _write_json_line({RESULT_KEY_OVER_PACE: None, RESULT_KEY_ERROR: str(unreadable)})
        return EXIT_CODE_UNREADABLE
    _write_json_line(verdict)
    return EXIT_CODE_OVER_PACE if verdict[RESULT_KEY_OVER_PACE] else EXIT_CODE_UNDER_PACE


if __name__ == "__main__":
    sys.exit(main())
