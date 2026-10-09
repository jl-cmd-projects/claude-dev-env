---
name: correction
description: Turn a correction the user just made into a short handoff brief they paste into a corrections intake, or land the fix in this session with the fix playbook. Use when the user types /correction followed by what the agent got wrong, or /correction fix to land the fix here.
argument-hint: "[fix] <what the agent got wrong, in the user's words>"
---

# /correction

The user corrected an agent and wants the fix to stick. Write one brief that records the correction. By default the user pastes it into the place that turns corrections into lasting fixes. When `$ARGUMENTS` starts with the word `fix`, this session lands the fix itself.

`$ARGUMENTS` is the user's statement of the correction, after a leading `fix` when one is present. Fill the other fields from this session: the transcript, the files and pull requests it touched, and the messages it sent. When the session does not settle a field, write `unknown` there.

Print the brief as one fenced `text` block:

```text
Correction: <$ARGUMENTS, word for word>
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
| Hand off, the default | Nothing. The brief is the whole reply. |
| `fix` | Run [`playbooks/fix.md`](playbooks/fix.md). |

## Layout

| File | What it holds |
|---|---|
| `SKILL.md` | The brief and the playbook index |
| `playbooks/fix.md` | The steps that land one correction as a control and a pull request in this session |
