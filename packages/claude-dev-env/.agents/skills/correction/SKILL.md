---
name: correction
description: Turn a correction the user made to an agent into a Suggested task card that starts a fix session in one click, list the corrections filed as issues before the card, write a handoff brief, or land the fix in this session with the fix playbook. Use when the user types /correction, /correction fix, says "file this as a correction", or asks to show the open corrections.
argument-hint: "[fix] <what the agent got wrong, in the user's words>"
---

# /correction

The user corrected an agent and wants the fix to stick. By default the correction becomes a Suggested task card, and the user starts the fix session from it in one click. No issue is filed. When `$ARGUMENTS` starts with the word `fix`, this session lands the fix itself: write the brief, then follow the fix playbook.

## Hand it off

Use this for `/correction <text>` and "file this as a correction: <text>".

1. Write the brief below, then build the card from it with [`scripts/correction_task_card.py`](scripts/correction_task_card.py). Pipe one JSON object in a quoted heredoc: `title` starts with a verb and stays under 60 characters, `tldr` is one plain sentence, `brief` is the brief block text, and `files` lists the repository-relative paths the brief names.
   ```bash
   python "${CLAUDE_SKILL_DIR}/scripts/correction_task_card.py" <<'CARD'
   {"title": "<verb first>", "tldr": "<one sentence>", "brief": "<brief block, newlines as \n>", "files": ["<repo-relative path>"]}
   CARD
   ```

2. When the session has `mcp__ccd_session__spawn_task`, call it with the `title`, `tldr`, and `prompt` the script prints. Reply with the card title.
3. Without that tool, run the script again with `--prompt-only` and print its output in one fenced `text` block as the handoff brief.

## List them

For "show the open corrections", run `python "${CLAUDE_SKILL_DIR}/scripts/correction_filing.py" list` and print its lines. It lists the issues filed before the card replaced filing, and the issues the correction flag mod still files.

## Brief

Print one fenced `text` block. Fill the fields from this session: the transcript, the files and pull requests it touched, and the messages it sent. Write `unknown` for a field the session does not settle.

```text
Correction: <$ARGUMENTS word for word, minus a leading fix>
Asked: <what the user asked for, quoted where a message carries it>
Agent did: <what the agent did, with the reply, file, or command that shows it>
Corrected to: <what the user wanted instead, or the fix already made>
Where: <repository, branch or pull request, files, tool, or thread>
Evidence: <file:line, log line, or quoted message that shows the miss>
Repeat: <yes, with the earlier time it happened | no | unknown>
```

Keep each field to one or two lines. Leave out the layer and the fix design; the intake or the fix playbook decides those.

## Playbooks

| Mode | What follows the brief |
|---|---|
| Hand off, the default | The task card, or the handoff brief when `spawn_task` is absent. |
| `fix` | Read [`playbooks/fix.md`](playbooks/fix.md) right after the brief, and run its steps from step 2. |

## Layout

| File | What it holds |
|---|---|
| `SKILL.md` | The handoff, the listing, the brief, and the playbook index |
| `playbooks/fix.md` | The steps that land one correction as a control and a pull request in this session |
| `scripts/correction_task_card.py` | Builds the `spawn_task` title, tldr, and standalone prompt from the brief and the fix playbook |
| `scripts/correction_task_card_constants/config/constants.py` | Card field rules and the prompt template |
| `scripts/test_correction_task_card.py` | Behavior tests for the card against the shipped fix playbook |
| `scripts/correction_filing.py` | Lists the open correction issues, and files one for the correction flag mod |
| `scripts/correction_filing_constants/config/constants.py` | Config keys, issue shape, and redaction patterns |
| `scripts/test_correction_filing.py` | Behavior tests with a stand-in `gh` |
| `references/filing.md` | Config file, issue shape, dedupe, and commands |
