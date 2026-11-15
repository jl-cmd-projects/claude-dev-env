"""Constants for the cloud SessionStart refresh hook.

``RefreshOutcome`` is the closed set of refresh outcomes that leave the
install not known to be current. Each member's value is the message the user
sees, so a new outcome cannot exist without one. The hook formats a message
with ``str.format`` and the fields ``version``, ``install_command``,
``timeout_seconds``, ``exit_code``, ``signal_number``, ``installed_version``,
``error`` and ``latest_install_command``.
"""

from enum import Enum

PACKAGE_NAME = "claude-dev-env"
MANIFEST_FILE_NAME = ".claude-dev-env-manifest.json"
CLAUDE_HOME_DIRECTORY_NAME = ".claude"
CONFIG_DIR_OVERRIDE_VARIABLE_NAME = "CLAUDE_CONFIG_DIR"
REMOTE_SESSION_VARIABLE_NAME = "CLAUDE_CODE_REMOTE"
REMOTE_SESSION_ACTIVE_VALUE = "true"
REGISTRY_VERSION_PATTERN = r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?"
REGISTRY_PROBE_TIMEOUT_SECONDS = 30
INSTALL_TIMEOUT_SECONDS = 570
IN_PROGRESS_RECORD_LIFETIME_SECONDS = INSTALL_TIMEOUT_SECONDS + 60
FAILED_INSTALL_RECORD_FILE_NAME = ".claude-dev-env-refresh-failed-version"
IN_PROGRESS_INSTALL_RECORD_FILE_NAME = ".claude-dev-env-refresh-in-progress"
VERSION_ORDER_PATTERN = r"(\d+)\.(\d+)\.(\d+)(-)?"
LATEST_INSTALL_COMMAND = "npx -y claude-dev-env@latest"
NO_INSTALLED_VERSION_TEXT = "no version"
MESSAGE_LINE_SEPARATOR = "\n"


class RefreshOutcome(Enum):
    LOOKUP_FAILED = (
        "claude-dev-env refresh: `npm view claude-dev-env version` gave no"
        " version, so this session cannot tell whether claude-dev-env is"
        " current. To install the latest, run `{latest_install_command}` from"
        " your home directory."
    )
    SKIPPED_FAILED_VERSION = (
        "claude-dev-env refresh: skipped {version}, because its install"
        " failed at an earlier session start. To retry, run `{install_command}`"
        " from your home directory."
    )
    INSTALLER_DID_NOT_START = (
        "claude-dev-env refresh: {version} did not install, because npx was"
        " not found on PATH or could not start. This session keeps the"
        " claude-dev-env it booted with. To install it, run `{install_command}`"
        " from your home directory."
    )
    INSTALL_TIMED_OUT = (
        "claude-dev-env refresh: the install of {version} ran past"
        " {timeout_seconds} seconds and was stopped before it ended, and the"
        " manifest shows {installed_version}. The next session start tries"
        " again. To install it now, run `{install_command}` from your home"
        " directory."
    )
    INSTALL_EXITED = (
        "claude-dev-env refresh: `{install_command}` failed with exit code"
        " {exit_code}, so this session keeps the claude-dev-env it booted with."
        " Later session starts skip {version} and try again at the next"
        " release. To retry now, run `{install_command}` from your home"
        " directory."
    )
    INSTALL_SIGNALLED = (
        "claude-dev-env refresh: the install of {version} was stopped by"
        " signal {signal_number} before it ended, and the manifest shows"
        " {installed_version}. The next session start tries again. To install"
        " it now, run `{install_command}` from your home directory."
    )
    INSTALL_LEFT_OLD_VERSION = (
        "claude-dev-env refresh: `{install_command}` exited 0, but the"
        " manifest shows {installed_version} instead of {version}. The next"
        " session start tries again. To install it now, run"
        " `{install_command}` from your home directory."
    )
    LAST_REFRESH_UNFINISHED = (
        "claude-dev-env refresh: the refresh hook was stopped at an earlier"
        " session start before its install of {version} ended, and the"
        " manifest shows {installed_version}. To install it, run"
        " `{install_command}` from your home directory."
    )
    HOOK_ERROR = (
        "claude-dev-env refresh: the refresh hook stopped on {error}, so this"
        " session cannot tell whether claude-dev-env is current. To install the"
        " latest, run `{latest_install_command}` from your home directory."
    )
