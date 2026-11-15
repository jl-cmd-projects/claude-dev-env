"""Constants for the cloud SessionStart refresh hook."""

PACKAGE_NAME = "claude-dev-env"
MANIFEST_FILE_NAME = ".claude-dev-env-manifest.json"
CLAUDE_HOME_DIRECTORY_NAME = ".claude"
CONFIG_DIR_OVERRIDE_VARIABLE_NAME = "CLAUDE_CONFIG_DIR"
REMOTE_SESSION_VARIABLE_NAME = "CLAUDE_CODE_REMOTE"
REMOTE_SESSION_ACTIVE_VALUE = "true"
REGISTRY_VERSION_PATTERN = r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?"
REGISTRY_PROBE_TIMEOUT_SECONDS = 30
INSTALL_TIMEOUT_SECONDS = 570
FAILED_INSTALL_RECORD_FILE_NAME = ".claude-dev-env-refresh-failed-version"
FAILED_INSTALL_MESSAGE_TEMPLATE = (
    "claude-dev-env refresh: `{install_command}` failed with exit code {exit_code},"
    " so this session keeps the claude-dev-env it booted with. Later session"
    " starts skip {registry_version} and try again at the next release. To retry"
    " now, run `{install_command}` from your home directory."
)
SKIPPED_INSTALL_MESSAGE_TEMPLATE = (
    "claude-dev-env refresh: skipped {registry_version}, because its install"
    " failed at an earlier session start. To retry, run `{install_command}` from"
    " your home directory."
)
