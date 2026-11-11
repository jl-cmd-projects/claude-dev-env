# v1

Installs the subagent model and effort rule and its guide into the workspace's `.claude/` folder, and registers `subagent_effort_route_hook.py` on `Agent|Task` in the workspace's `.claude/settings.json`.

The baseline installs nothing and registers no hook. Every other input is the same in both arms: the fixture project, the case prompt, the parent model and effort (Opus at high), the turn cap, the allowed tools and `--setting-sources project,local`. That flag keeps the home config's rules, hooks and skills out of both arms.

The rule file is path-scoped to agent, skill, hook and workflow files, as it ships, so in this fixture project it may never load. The v1 numbers are mostly the hook's.
