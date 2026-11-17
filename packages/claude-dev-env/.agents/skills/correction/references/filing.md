# Correction filing

`scripts/correction_filing.py` posts a correction as an issue labelled `correction` on the repository of the corrected work. `/correction` runs it for every correction, and the correction flag mod in claude-mods-framework runs `correction_filing.py file --source flag`.

## Which repository

The issue goes to the GitHub repository of `--checkout`, else of the working directory. The script reads that checkout's `origin` remote, so a worktree resolves to the repository it belongs to. Before posting, it asks GitHub whether the repository is reachable and has issues turned on, and whether it is public.

When that repository cannot take the issue, the script posts on the correction inbox and appends a `fallback` note with the reason to its result line. The reasons are: the checkout has no `origin` remote (a session with no repository), `origin` is not on GitHub, GitHub cannot reach the repository (no access, or it does not exist), or the repository has issues turned off. When the inbox is missing or also unusable, it posts nothing, exits 1, and prints every reason.

## Fallback inbox

The inbox is the `repository` key of `~/.claude/correction-capture.json`, or of the file `CLAUDE_CORRECTION_CAPTURE_PATH` names:

```json
{"repository": "owner/name"}
```

Keep this file private. An older file that also has a `label` key still works; the label is always `correction`.

## Issue shape

- Title: `Correction: ` and the first 72 characters of the brief's `Correction:` line, or of the text when it has none.
- Body: the `--preamble-file` sections first, when given, then a `## Correction` section that tells the reader how to pick the issue up, the source (`typed`, `flag`, `reaction`, or `hook`), a repeat line when it repeats a closed issue, the text as a quote, and two hidden markers.
- The script masks GitHub, OpenAI, Slack, and AWS tokens and email addresses. On a public repository it also masks drive and home paths, the local account name, and links to other GitHub repositories.
- The script runs the managed `scripts/durable_post_lint.py --action issue-create` (or `issue-comment`) on the body, under `CLAUDE_CONFIG_DIR`, else `~/.claude`. A finding stops the post, and the script prints it.
- The script creates the `correction` label when the repository lacks it, then applies it.

## Dedupe and repeats

One marker keys the correction: a hash of `--dedupe-key` when given, else of the whitespace-collapsed `Correction:` line. The other keys this exact text. Before posting, the script checks `correction-capture-filed.json` beside the config file, then every `correction` issue, open and closed.

- The same text again prints `Already filed: <url>`.
- A new text for a correction with an open issue posts a `## Repeat` comment on it and prints `Repeat marked on <issue>: <comment>`.
- A new text for a correction whose issue is closed posts a new issue that links the closed one and prints `Filed: <url>, a repeat of <closed url>`.

The local file covers the minute after posting, when the labeled-issue listing can miss a new issue.

## Commands

Without `--text`, `file` reads the correction from standard input.

```bash
python correction_filing.py file [--checkout <dir>] [--preamble-file <file>] [--text "<text>"] [--source flag] [--dedupe-key <id>]
python correction_filing.py list [--checkout <dir>]
```
