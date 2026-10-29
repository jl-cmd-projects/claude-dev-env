Every rule below is always on. When the rule's trigger matches, read the file and follow it in full. Link targets resolve under `~/.claude/`.

- **Core** ([`~/.claude/docs/agents-guidance/core.md`](docs/agents-guidance/core.md)). Every reply and file edit: status, diffs, verdicts, writes, edit gate, scope.
- **Evidence** ([guide](docs/agents-guidance/evidence.md)). Every claim and report.
- **Asks** ([guide](docs/agents-guidance/asks.md)). Every ask from the user.
- **Prose** ([guide](docs/agents-guidance/prose.md)). Read it before you write a reply, doc, commit, or PR body.
- **Tools** ([guide](docs/agents-guidance/tools.md)). Every tool call and its output.
- **Comments** ([full text](docs/CODE_RULES.md#comment-preservation)). Do not add code comments. Preserve existing comments. Docstrings remain allowed. When a change touches code that an existing comment describes or is attached to, remove that comment in the same change. Leave comments tied to untouched code unchanged. Keep comment cleanup inside the requested task. Production and tests follow one rule. Changed directive, TODO, FIXME, HACK, XXX, and type-ignore comments are removed.
- **Banned word: real** ([full text](docs/agents-guidance/banned-word.md)). Never write real, really, or real-world. This ban has no exception. Swapping in actual, actually, genuine, or true is the same move, and each is banned with it.
- **No PR until proven** ([full text](docs/rule-guides/proof-before-pull-request.md)). Never open a pull request until the change is proven to work on the target system.
