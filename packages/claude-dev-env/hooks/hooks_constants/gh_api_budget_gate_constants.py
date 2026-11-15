"""Constants for the gate that keeps agents from draining the GitHub API limit.

Holds the gh command paths that watch a run, the shell loop keywords and sleep
spellings the loop reader knows, the table of gh reads that draw on the core
REST limit, the rate limit query and its cache file, the four fifths rule, and
the three deny messages.
"""

from __future__ import annotations

import re

__all__ = [
    "GH_PROGRAM_NAME",
    "GH_COMMAND_PATH_LENGTH",
    "ALL_GH_RUN_WATCH_COMMAND_WORDS",
    "ALL_GH_PR_CHECKS_COMMAND_WORDS",
    "GH_WATCH_OPTION",
    "WATCH_PROGRAM_NAME",
    "ALL_WATCH_INTERVAL_OPTIONS",
    "ALL_WATCH_OPTIONS_WITH_A_VALUE",
    "WATCH_SHORT_INTERVAL_OPTION",
    "WATCH_LONG_INTERVAL_OPTION_PREFIX",
    "WATCH_DEFAULT_INTERVAL_SECONDS",
    "ALL_LOOP_KEYWORDS",
    "ALL_CONDITION_LOOP_KEYWORDS",
    "ALL_BASH_LOOP_HEADER_KEYWORDS",
    "ALL_LEADING_SHELL_KEYWORDS",
    "COUNTED_LOOP_KEYWORD",
    "LOOP_BODY_KEYWORD",
    "LOOP_END_KEYWORD",
    "BLOCK_START_CHARACTER",
    "BLOCK_END_CHARACTER",
    "ALL_QUOTE_CHARACTERS",
    "LOOP_HEADER_OPENER",
    "LOOP_HEADER_CHARACTERS",
    "ENDLESS_FOR_HEADER_MARKER",
    "ALL_ENDLESS_CONDITIONS_BY_LOOP_KEYWORD",
    "ALL_SLEEP_PROGRAM_NAMES",
    "SLEEP_DURATION_PATTERN",
    "SLEEP_DURATION_AMOUNT_GROUP",
    "SLEEP_DURATION_UNIT_GROUP",
    "SECONDS_BY_SLEEP_UNIT",
    "SLEEP_TIMESPAN_PATTERN",
    "SLEEP_TIMESPAN_FIELD_SEPARATOR",
    "ALL_SECONDS_BY_TIMESPAN_FIELD",
    "ALL_SHELL_EXPANSION_MARKERS",
    "OPTION_PREFIX",
    "SLEEP_PARAMETER_VALUE_SEPARATOR",
    "START_SLEEP_SECONDS_PARAMETER",
    "START_SLEEP_MILLISECONDS_PARAMETER",
    "START_SLEEP_DURATION_PARAMETER",
    "MINIMUM_START_SLEEP_DURATION_PARAMETER_LENGTH",
    "MINIMUM_START_SLEEP_PARAMETER_LENGTH",
    "MILLISECONDS_PER_SECOND",
    "BLOCK_CLOSER_CHARACTERS",
    "MINIMUM_POLL_INTERVAL_SECONDS",
    "POWERSHELL_VARIABLE_PATTERN",
    "ALL_POWERSHELL_ASSIGNMENT_OPERATORS",
    "POWERSHELL_ASSIGNMENT_PREFIX_LENGTH",
    "ALL_GH_READ_SUBCOMMANDS_BY_COMMAND_GROUP",
    "ALL_GH_READ_COMMAND_GROUPS",
    "ALL_GH_API_METHOD_OPTIONS",
    "GH_API_SHORT_METHOD_OPTION",
    "ALL_GH_API_READ_METHODS",
    "ALL_GH_API_BODY_OPTIONS",
    "ALL_GH_API_SHORT_BODY_OPTIONS",
    "GH_SHORT_OPTION_LENGTH",
    "ALL_GH_API_UNBUDGETED_ENDPOINTS",
    "ALL_RATE_LIMIT_QUERY_ARGUMENTS",
    "RATE_LIMIT_QUERY_TIMEOUT_SECONDS",
    "RATE_LIMIT_RESOURCES_KEY",
    "RATE_LIMIT_CORE_KEY",
    "CACHE_DIRECTORY_NAME",
    "CACHE_FILE_NAME",
    "CACHE_TEMPORARY_SUFFIX",
    "CACHE_MAXIMUM_AGE_SECONDS",
    "CACHE_READ_AT_KEY",
    "LIMIT_KEY",
    "USED_KEY",
    "RESET_KEY",
    "SPENT_FRACTION_NUMERATOR",
    "SPENT_FRACTION_DENOMINATOR",
    "RESET_TIME_FORMAT",
    "GATE_HOOK_NAME",
    "WATCH_COMMAND_DENY_REASON",
    "TIGHT_POLLING_LOOP_DENY_REASON",
    "SPENT_BUDGET_DENY_REASON_TEMPLATE",
    "SPENT_BUDGET_RESET_SENTENCE_TEMPLATE",
]

GH_PROGRAM_NAME: str = "gh"
GH_COMMAND_PATH_LENGTH: int = 2
ALL_GH_RUN_WATCH_COMMAND_WORDS: tuple[str, str] = ("run", "watch")
ALL_GH_PR_CHECKS_COMMAND_WORDS: tuple[str, str] = ("pr", "checks")
GH_WATCH_OPTION: str = "--watch"

WATCH_PROGRAM_NAME: str = "watch"
ALL_WATCH_INTERVAL_OPTIONS: frozenset[str] = frozenset({"-n", "--interval"})
ALL_WATCH_OPTIONS_WITH_A_VALUE: frozenset[str] = frozenset({"-q", "--equexit"})
WATCH_SHORT_INTERVAL_OPTION: str = "-n"
WATCH_LONG_INTERVAL_OPTION_PREFIX: str = "--interval="
WATCH_DEFAULT_INTERVAL_SECONDS: float = 2.0

ALL_LOOP_KEYWORDS: frozenset[str] = frozenset(
    {"while", "until", "for", "foreach", "do", "foreach-object", "%"}
)
ALL_CONDITION_LOOP_KEYWORDS: frozenset[str] = frozenset({"while", "until"})
ALL_BASH_LOOP_HEADER_KEYWORDS: frozenset[str] = frozenset({"while", "until", "for"})
ALL_LEADING_SHELL_KEYWORDS: frozenset[str] = frozenset({"then", "else", "elif", "{", "!", "time"})
COUNTED_LOOP_KEYWORD: str = "for"
LOOP_BODY_KEYWORD: str = "do"
LOOP_END_KEYWORD: str = "done"
BLOCK_START_CHARACTER: str = "{"
BLOCK_END_CHARACTER: str = "}"
ALL_QUOTE_CHARACTERS: str = "\"'"
LOOP_HEADER_OPENER: str = "("
LOOP_HEADER_CHARACTERS: str = "(); "
ENDLESS_FOR_HEADER_MARKER: str = ";;"
ALL_ENDLESS_CONDITIONS_BY_LOOP_KEYWORD: dict[str, frozenset[str]] = {
    "while": frozenset({"true", ":", "$true", "1"}),
    "until": frozenset({"false", "$false"}),
}

ALL_SLEEP_PROGRAM_NAMES: frozenset[str] = frozenset({"sleep", "start-sleep"})
SLEEP_DURATION_PATTERN: re.Pattern[str] = re.compile(r"(?P<amount>\d+(?:\.\d*)?|\.\d+)(?P<unit>[smhd]?)")
SLEEP_DURATION_AMOUNT_GROUP: str = "amount"
SLEEP_DURATION_UNIT_GROUP: str = "unit"
SECONDS_BY_SLEEP_UNIT: dict[str, float] = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
SLEEP_TIMESPAN_PATTERN: re.Pattern[str] = re.compile(r"\d+:\d+(?::\d+(?:\.\d+)?)?")
SLEEP_TIMESPAN_FIELD_SEPARATOR: str = ":"
ALL_SECONDS_BY_TIMESPAN_FIELD: tuple[float, ...] = (3600.0, 60.0, 1.0)
ALL_SHELL_EXPANSION_MARKERS: tuple[str, ...] = ("$", "`")
OPTION_PREFIX: str = "-"
SLEEP_PARAMETER_VALUE_SEPARATOR: str = ":"
START_SLEEP_SECONDS_PARAMETER: str = "-seconds"
START_SLEEP_MILLISECONDS_PARAMETER: str = "-milliseconds"
START_SLEEP_DURATION_PARAMETER: str = "-duration"
MINIMUM_START_SLEEP_DURATION_PARAMETER_LENGTH: int = 3
MINIMUM_START_SLEEP_PARAMETER_LENGTH: int = 2
MILLISECONDS_PER_SECOND: float = 1000.0
BLOCK_CLOSER_CHARACTERS: str = "})"
MINIMUM_POLL_INTERVAL_SECONDS: float = 60.0

POWERSHELL_VARIABLE_PATTERN: re.Pattern[str] = re.compile(r"\$(?:\{[^}]*\}|[\w:]+)")
ALL_POWERSHELL_ASSIGNMENT_OPERATORS: frozenset[str] = frozenset(
    {"=", "+=", "-=", "*=", "/=", "%=", "??="}
)
POWERSHELL_ASSIGNMENT_PREFIX_LENGTH: int = 2

ALL_GH_READ_SUBCOMMANDS_BY_COMMAND_GROUP: dict[str, frozenset[str]] = {
    "pr": frozenset({"view", "list", "status", "checks", "diff"}),
    "issue": frozenset({"view", "list", "status"}),
    "run": frozenset({"view", "list", "download"}),
    "release": frozenset({"view", "list", "download"}),
    "repo": frozenset({"view", "list"}),
    "workflow": frozenset({"view", "list"}),
    "gist": frozenset({"view", "list"}),
    "cache": frozenset({"list"}),
    "label": frozenset({"list"}),
    "ruleset": frozenset({"view", "list", "check"}),
    "secret": frozenset({"list"}),
    "variable": frozenset({"list", "get"}),
    "org": frozenset({"list"}),
    "project": frozenset({"view", "list", "field-list", "item-list"}),
}
ALL_GH_READ_COMMAND_GROUPS: frozenset[str] = frozenset({"search", "status"})
ALL_GH_API_METHOD_OPTIONS: frozenset[str] = frozenset({"-X", "--method"})
GH_API_SHORT_METHOD_OPTION: str = "-X"
ALL_GH_API_READ_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})
ALL_GH_API_BODY_OPTIONS: frozenset[str] = frozenset(
    {"-f", "-F", "--field", "--raw-field", "--input"}
)
ALL_GH_API_SHORT_BODY_OPTIONS: frozenset[str] = frozenset({"-f", "-F"})
GH_SHORT_OPTION_LENGTH: int = 2
ALL_GH_API_UNBUDGETED_ENDPOINTS: frozenset[str] = frozenset({"graphql", "rate_limit"})

ALL_RATE_LIMIT_QUERY_ARGUMENTS: tuple[str, ...] = ("gh", "api", "rate_limit")
RATE_LIMIT_QUERY_TIMEOUT_SECONDS: float = 10.0
RATE_LIMIT_RESOURCES_KEY: str = "resources"
RATE_LIMIT_CORE_KEY: str = "core"
CACHE_DIRECTORY_NAME: str = "cache"
CACHE_FILE_NAME: str = "gh_api_budget.json"
CACHE_TEMPORARY_SUFFIX: str = ".tmp"
CACHE_MAXIMUM_AGE_SECONDS: float = 300.0
CACHE_READ_AT_KEY: str = "read_at"
LIMIT_KEY: str = "limit"
USED_KEY: str = "used"
RESET_KEY: str = "reset"
SPENT_FRACTION_NUMERATOR: int = 4
SPENT_FRACTION_DENOMINATOR: int = 5
RESET_TIME_FORMAT: str = "%Y-%m-%d %H:%M UTC"

GATE_HOOK_NAME: str = "gh_api_budget_gate.py"
WATCH_COMMAND_DENY_REASON: str = (
    "BLOCKED: gh run watch and gh pr checks --watch poll the GitHub API every few seconds "
    "until the run ends, and that drains the shared API limit. "
    "Make one timed read instead. Run a background loop that sleeps at least 60 seconds "
    "between gh run view calls, such as "
    "`while :; do gh run view $RUN_ID --json status -q .status | grep -q completed && break; "
    "sleep 60; done`, or make a single gh run view read when the task notification arrives."
)
TIGHT_POLLING_LOOP_DENY_REASON: str = (
    "BLOCKED: this shell loop calls gh with less than 60 seconds of sleep between calls, "
    "and that drains the shared GitHub API limit. "
    "Sleep at least 60 seconds between gh calls, such as sleep 60 in Bash "
    "or Start-Sleep -Seconds 60 in PowerShell."
)
SPENT_BUDGET_DENY_REASON_TEMPLATE: str = (
    "BLOCKED: the GitHub core API limit is {used} of {limit} used, four fifths or more, "
    "so gh reads wait until it resets. {reset_sentence}"
    "Wait for the reset, or read files already in the checkout with git, "
    "such as git log, git show, or git diff."
)
SPENT_BUDGET_RESET_SENTENCE_TEMPLATE: str = "It resets at {reset_time}. "
