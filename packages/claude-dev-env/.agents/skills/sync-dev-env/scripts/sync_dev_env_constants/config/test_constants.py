from sync_dev_env_constants.config import constants


def test_paths_match_the_claude_code_plugin_layout() -> None:
    assert constants.INSTALLED_PLUGINS_RELATIVE_PATH.parts == (
        "plugins",
        "installed_plugins.json",
    )
    assert constants.PLUGIN_CACHE_RELATIVE_PATH.parts == ("plugins", "cache")
    assert constants.DEFAULT_CLAUDE_HOME.name == ".claude"


def test_keys_match_the_claude_code_settings_files() -> None:
    assert (
        constants.ENABLED_PLUGINS_KEY,
        constants.PLUGINS_KEY,
        constants.INSTALL_PATH_KEY,
        constants.LAST_UPDATED_KEY,
    ) == ("enabledPlugins", "plugins", "installPath", "lastUpdated")
