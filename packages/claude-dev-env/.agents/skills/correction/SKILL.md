---
name: correction
description: File a correction the user made to an agent as one labeled GitHub issue, list the open corrections, write a handoff brief, or land the fix in this session with the fix playbook. Use when the user types /correction, /correction fix, says "file this as a correction", or asks to show the open corrections.
argument-hint: "[fix] <what the agent got wrong, in the user's words>"
---

# /correction

The user corrected an agent and wants the fix to stick. A labeled issue is the shared store a corrections project watches. When `$ARGUMENTS` starts with the word `fix`, this session lands the fix itself: write the brief, then follow the fix playbook.

## File it

Use this for `/correction <text>` and "file this as a correction: <text>". Run:

```bash
python "${CLAUDE_SKILL_DIR}/scripts/correction_filing.py" file <<'CORRECTION'
<the correction, word for word>
CORRECTION
```

Pass the user's words exactly. The quoted heredoc keeps the shell from expanding `$`, backticks, and quotes in them. Print the one line the command prints, `Filed: <url>` or `Already filed: <url>`, and nothing else.

When it prints `No correction filing config`, write the brief below instead and tell the user the config file it names.

## List them

For "show the open corrections", run `python "${CLAUDE_SKILL_DIR}/scripts/correction_filing.py" list` and print its lines.

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
| File, the default | The filed line, or the brief when no config exists. |
| `fix` | Read [`playbooks/fix.md`](playbooks/fix.md) right after the brief, and run its steps from step 2. |

## Layout

| File | What it holds |
|---|---|
| `SKILL.md` | Filing, the brief, and the playbook index |
| `playbooks/fix.md` | The steps that land one correction as a control and a pull request in this session |
| `scripts/correction_filing.py` | Files one correction as a labeled issue, deduplicated, or lists the open ones |
| `scripts/correction_filing_constants/config/constants.py` | Config keys, issue shape, and redaction patterns |
| `scripts/test_correction_filing.py` | Behavior tests with a stand-in `gh` |
| `references/filing.md` | Config file, issue shape, dedupe, and commands |
