# Correction filing

`scripts/correction_filing.py` files a correction as a labeled issue for the correction flag mod in claude-mods-framework, which runs `correction_filing.py file --source flag`. `/correction` hands a correction off as a task card and files no issue. The skill runs only `list`, which reads the issues filed before the card and the issues the flag mod files.

## Config

The script reads `~/.claude/correction-capture.json`, or the file `CLAUDE_CORRECTION_CAPTURE_PATH` names:

```json
{"repository": "owner/name", "label": "correction"}
```

Keep this file private. Without it the script files nothing and exits 1.

## Issue shape

- Title: `Correction: ` and the first 72 characters of the text.
- Body: the source (`typed`, `flag`, `reaction`, or `hook`), the text as a quote, and a hidden dedupe marker.
- The script masks GitHub, OpenAI, Slack, and AWS tokens and email addresses before filing.
- The script applies the label itself.

## Dedupe

The key is a hash of `--dedupe-key` when given, else of the whitespace-collapsed text. A caller with a message id passes it there. Before filing, the script checks `correction-capture-filed.json` beside the config file for this repository and key, then every labeled issue, open and closed, and prints `Already filed: <url>` on a key match. The local file covers the minute after filing, when the labeled-issue listing can miss a new issue.

## Commands

Without `--text`, `file` reads the correction from standard input.

```bash
python correction_filing.py file [--text "<text>"] [--source flag] [--dedupe-key <id>]
python correction_filing.py list
```
