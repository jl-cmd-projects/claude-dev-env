# DeepStack install

The plugin lives in `jl-cmd-projects/DeepStack`. `npx claude-dev-env` installs plugin id `deepstack@DeepStack` for Claude Code and Codex, and copies it to `~/.cursor/plugins/deepstack` with the SessionStart hook and the first-task gate.

The entry skill in that repository names these triggers:

- DeepStack intake
- DeepStack search leaf
- DeepStack reproducible-check leaf
