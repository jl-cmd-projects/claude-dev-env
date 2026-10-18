import json
import shlex

from hooks_constants import haiku_spawn_slim_gate_constants as constants


def test_slim_profile_command_passes_settings_and_mcp_config() -> None:
    command = shlex.split(constants.SLIM_PROFILE_SHELL_COMMAND)

    assert command == [constants.SLIM_PROFILE_EXECUTABLE, *constants.ALL_SLIM_PROFILE_ARGUMENTS]
    assert command[command.index("--model") + 1] == "haiku"
    assert json.loads(command[command.index("--settings") + 1])["autoMemoryEnabled"] is False
    assert json.loads(command[command.index("--mcp-config") + 1]) == {"mcpServers": {}}


def test_deny_reason_includes_the_command_and_environment() -> None:
    assert constants.SLIM_PROFILE_SHELL_COMMAND in constants.SLIM_PROFILE_DENY_REASON
    assert constants.SLIM_PROFILE_ENVIRONMENT_TEXT in constants.SLIM_PROFILE_DENY_REASON
