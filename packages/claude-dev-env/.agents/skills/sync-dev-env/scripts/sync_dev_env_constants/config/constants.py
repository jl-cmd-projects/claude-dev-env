"""Paths, file keys, and report lines for the link_plugin_skills script."""

from pathlib import Path

DEFAULT_CLAUDE_HOME = Path.home() / ".claude"
INSTALLED_PLUGINS_RELATIVE_PATH = Path("plugins") / "installed_plugins.json"
PLUGIN_CACHE_RELATIVE_PATH = Path("plugins") / "cache"
SETTINGS_FILE_NAME = "settings.json"
SKILLS_DIRECTORY_NAME = "skills"
SKILL_MANIFEST_FILE_NAME = "SKILL.md"
ENABLED_PLUGINS_KEY = "enabledPlugins"
PLUGINS_KEY = "plugins"
INSTALL_PATH_KEY = "installPath"
LAST_UPDATED_KEY = "lastUpdated"
CREATED_REPORT = "linked {name} -> {target}"
REPOINTED_REPORT = "re-pointed {name} -> {target}"
REMOVED_REPORT = "removed {name} (its skill left the plugin or the plugin is off)"
SKIPPED_REPORT = (
    "skipped {name}: a skill the plugin does not own already uses that name"
)
SUMMARY_REPORT = "{linked} linked, {repointed} re-pointed, {removed} removed, {skipped} skipped, {kept} unchanged"
LINKED_OUTCOME = "linked"
REPOINTED_OUTCOME = "repointed"
REMOVED_OUTCOME = "removed"
SKIPPED_OUTCOME = "skipped"
KEPT_OUTCOME = "kept"
