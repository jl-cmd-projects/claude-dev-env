# v1

Installs the always-on rule `features-start-with-an-eval.md` and its rule guide into the workspace's `.claude/` folder.

The baseline installs nothing. Every other input is the same in both arms: the fixture project, the case prompt, the model, the effort, the turn cap and `--setting-sources project,local`. That flag keeps the home config's rules, hooks and skills out of both arms, so the baseline stays a baseline after the rule ships.
