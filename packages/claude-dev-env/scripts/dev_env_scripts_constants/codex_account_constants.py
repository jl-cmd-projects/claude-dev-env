"""Named constants for the Codex accounts a runner job picks between.

Each account signs in under its own Codex home. The picker reads every
account's rate-limit windows through ``codex app-server`` and names the account
a job runs on, trying the accounts in roster order.
"""

from __future__ import annotations

from dev_env_scripts_constants.claude_account_constants import LauncherProgram

ALL_CODEX_ACCOUNT_NAMES: tuple[str, ...] = ("codex-1", "codex-2", "codex-3", "codex-4")
"""Fallback Codex accounts, in try order, when no account roster is saved or set."""

CODEX_ACCOUNT_PROFILES_ENVIRONMENT_VARIABLE: str = "CODEX_ACCOUNT_PROFILES"
"""Environment variable naming the account roster, comma-separated, over the saved file."""

CODEX_ACCOUNT_LAUNCHERS_FILE_NAME: str = "account-launchers.json"
"""File under the profiles root that holds the saved account roster as a JSON list."""

CODEX_ACCOUNT_NAME_SEPARATOR: str = ","
"""Separator between account names in the roster environment variable."""

SETUP_PROMPT_TEXT: str = "Name for this Codex account launcher (blank to finish): "
"""Prompt the setup command shows for each account name."""

SETUP_SAVED_NAMES_TEMPLATE: str = "Saved Codex account launchers: {names}"
"""Line the setup command prints first, naming the saved roster."""

SETUP_NO_SAVED_NAMES_TEXT: str = "none"
"""Saved-roster text when no account launcher is saved."""

SETUP_NAMES_SEPARATOR: str = ", "
"""Separator between names on the setup command's saved-roster line."""

INVALID_ACCOUNT_ROSTER_TEMPLATE: str = "{source} names {name!r}: {reason}"
"""Error when the roster environment variable or file names an invalid account."""

ROSTER_NOT_A_LIST_TEMPLATE: str = "{source} must hold a JSON list of account names"
"""Error when the roster JSON is anything other than a list of names."""

ROSTER_JSON_INDENT: int = 2
"""Indent of the saved roster JSON, one name per line."""

COMMAND_SETUP: str = "setup"
"""Command that asks for the roster, saves it, and installs every launcher."""

COMMAND_INSTALL: str = "install"
"""Command that installs every saved roster account without asking."""

UNKNOWN_ACCOUNT_TEMPLATE: str = "unknown Codex account {name!r}; known: {known}"
"""Error when ``check`` names an account outside the roster."""

JSON_INSTALLED_KEY: str = "installed"
"""Setup JSON key holding the install report for every roster account."""

JSON_RETIRED_KEY: str = "retired"
"""Setup JSON key holding each dropped account and where its launcher moved."""

CODEX_PROFILES_ROOT_DIRECTORY_NAME: str = ".codex-profiles"
"""Directory under the user home that holds one Codex home per account."""

CODEX_PROFILES_ROOT_ENVIRONMENT_VARIABLE: str = "CODEX_PROFILES_ROOT"
"""Environment variable that relocates the Codex profiles root."""

MAIN_CODEX_HOME_DIRECTORY_NAME: str = ".codex"
"""Directory under the user home that holds the shared Codex setup."""

NO_ROSTER_ACCOUNT_NAME: str = "default"
"""Account name the broker gives the shared Codex home when no roster is configured."""

CODEX_HOME_ENVIRONMENT_VARIABLE: str = "CODEX_HOME"
"""Environment variable that points Codex at one account's home."""

CODEX_AUTH_FILE_NAME: str = "auth.json"
"""File in a Codex home that holds that account's sign-in."""

ALL_SHARED_CODEX_HOME_NAMES: frozenset[str] = frozenset(
    {
        "AGENTS.md",
        "agents",
        "config.toml",
        "hooks",
        "hooks.json",
        "plugins",
        "prompts",
        "rules",
        "skills",
    }
)
"""Codex home entries every account shares. Every other entry stays per account."""

NORMAL_TIER_MINIMUM_PERCENT_LEFT: float = 10.0
"""An account runs a job at its normal model only above this percent left."""

LUNA_TIER_STOP_PERCENT_LEFT: float = 1.0
"""A Luna fallback job stops once its account is at or below this percent left."""

LUNA_TIER_SHORT_WINDOW_MINIMUM_PERCENT_LEFT: float = 20.0
"""An account with a window shorter than a week runs Luna only with this much of it left."""

WEEKLY_WINDOW_MINUTES: int = 10080
"""Length of the weekly window. Any shorter window is a short window, such as 5 hours."""

FULL_PERCENT: float = 100.0
"""Percent scale ceiling, so percent left is this minus percent used."""

TIER_NORMAL: str = "normal"
"""Picker answer: run the job at its normal model on the named account."""

TIER_LUNA: str = "luna"
"""Picker answer: every account is at or under the bar, so Luna runs the job."""

TIER_WAIT: str = "wait"
"""Picker answer: no account has room, so the job waits."""

ALL_CODEX_BINARY_CANDIDATE_RELATIVE_PARTS: tuple[tuple[str, ...], ...] = (
    ("AppData", "Local", "Programs", "OpenAI", "Codex", "bin", "codex.exe"),
)
"""Install paths under the user home tried when ``codex`` is not on PATH."""

CODEX_BINARY_NAME: str = "codex"
"""Codex command name looked up on PATH."""

CODEX_LAUNCHER_PROGRAM: LauncherProgram = LauncherProgram(
    program=CODEX_BINARY_NAME,
    environment_variable=CODEX_HOME_ENVIRONMENT_VARIABLE,
    file_name_template="codex-{profile_name}.cmd",
)
"""Launcher that runs Codex with ``CODEX_HOME`` set to the account's home."""

ALL_APP_SERVER_ARGUMENTS: tuple[str, ...] = ("app-server", "--listen", "stdio://")
"""Arguments that start Codex as a JSON-RPC server on standard input and output."""

APP_SERVER_TIMEOUT_SECONDS: float = 30.0
"""Longest wait for the rate-limit reply before the read counts as failed."""

READER_JOIN_TIMEOUT_SECONDS: float = 2.0
"""Longest wait for the output reader to finish after the server stops."""

PROCESS_WAIT_TIMEOUT_SECONDS: float = 5.0
"""Longest wait to reap the server after its process tree is stopped."""

JSONRPC_VERSION: str = "2.0"
"""JSON-RPC protocol version on every message."""

INITIALIZE_REQUEST_ID: int = 1
"""Request id of the initialize handshake."""

RATE_LIMITS_REQUEST_ID: int = 2
"""Request id of the rate-limit read."""

METHOD_INITIALIZE: str = "initialize"
"""JSON-RPC method that opens the session."""

METHOD_INITIALIZED: str = "initialized"
"""JSON-RPC notification that confirms the session opened."""

METHOD_RATE_LIMITS_READ: str = "account/rateLimits/read"
"""JSON-RPC method that returns the account's rate-limit windows."""

CLIENT_NAME: str = "codex-account-choice"
"""Client name the handshake reports."""

CLIENT_VERSION: str = "1.0.0"
"""Client version the handshake reports."""

ALL_WINDOW_KEYS: tuple[str, ...] = ("primary", "secondary")
"""Keys under ``rateLimits`` that each hold one usage window."""

EXIT_CODE_ROOM: int = 0
"""Check answer: the account is above the floor."""

EXIT_CODE_NO_ROOM: int = 3
"""Check answer: the account is at or below the floor, or its meter is unread."""

REASON_NORMAL_TEMPLATE: str = "{account} has {percent_left:.0f}% left"
"""Reason when an account takes the job at its normal model."""

REASON_LUNA_TEMPLATE: str = (
    "every account is at or under {bar:.0f}% left; {account} has"
    " {percent_left:.0f}% and runs Luna until {stop:.0f}%"
)
"""Reason when the job falls back to Luna."""

REASON_WAIT_TEMPLATE: str = "no account has room; {account} resets first, at {reset}"
"""Reason when every account is out of room."""

REASON_WAIT_UNREAD: str = "no account meter could be read"
"""Reason when no account's meter reads at all."""

UNREAD_NOT_SIGNED_IN: str = "not signed in"
"""Unread reason when the account's Codex home holds no sign-in."""

UNKNOWN_RESET_TEXT: str = "an unknown time"
"""Reset text when no blocking window carries a reset time."""

TEXT_ENCODING: str = "utf-8"
"""Encoding for the server pipes and the JSON reports."""
