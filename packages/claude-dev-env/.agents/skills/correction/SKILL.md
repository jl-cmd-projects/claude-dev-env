---
name: correction
description: Post a correction as an issue labelled correction on the repository of the corrected work, list the open correction issues, or, on a typed /correction fix, land the fix in this session with the fix playbook. Use when the user corrects an agent, types /correction or /correction fix, says "file this as a correction", or asks to show the open corrections.
argument-hint: "[fix] <what the agent got wrong, in the user's words>"
---

# /correction

The user corrected an agent and wants the lesson fixed on purpose. By default the correction becomes an issue labelled `correction` on the repository of the corrected work, and the agent builds no control and opens no pull request for it. A later session picks up the issue. Only when the user types `/correction fix` does this session land the fix itself: post the issue, then follow the fix playbook.

## Post the issue

Use this for `/correction <text>`, "file this as a correction: <text>", and a correction the user gives with no command.

1. Fix the instance in front of you first.
2. Write the brief below.
3. Pick the checkout. It is the checkout or worktree of the repository whose work the user corrected, normally the session's working directory. When the corrected work spans two repositories, use the one the brief's `Where` line names first. When the correction covers both, post once from each.
4. Read that repository's own issue rules: its `AGENTS.md` or `CLAUDE.md` lines that name issues. When they require a section, such as a `## Request` section, write it to a file and pass `--preamble-file`.
5. Post it from a quoted heredoc, so the shell expands nothing:
   ```bash
   python "${CLAUDE_SKILL_DIR}/scripts/correction_filing.py" file --checkout "<checkout>" [--preamble-file <file>] <<'BRIEF'
   <brief block text>
   BRIEF
   ```
6. Name the issue in your reply with the line the script prints: `Filed`, `Repeat marked`, or `Already filed`, and the link. When the line carries a `fallback` note, say why the issue went to the inbox. When the script exits 1, print the brief in your reply and give its reason.

The script creates the `correction` label when the repository lacks it, masks secrets, and masks personal detail on a public repository. A repeat of an open issue becomes a comment on it. A repeat of a closed issue becomes a new issue that links it. [`references/filing.md`](references/filing.md) holds the repository choice, the fallback inbox, and the issue shape.

## List them

For "show the open corrections", run `python "${CLAUDE_SKILL_DIR}/scripts/correction_filing.py" list --checkout "<checkout>"` and print its lines.

## Brief

Print one fenced `text` block, and post the same text. Fill the fields from this session: the transcript, the files and pull requests it touched, and the messages it sent. Write `unknown` for a field the session does not settle.

```text
Correction: <$ARGUMENTS word for word, minus a leading fix>
Asked: <what the user asked for, quoted where a message carries it>
Agent did: <what the agent did, with the reply, file, or command that shows it>
Corrected to: <what the user wanted instead, or the fix already made>
Where: <repository, branch or pull request, files, tool, or thread>
Evidence: <file:line, log line, or quoted message that shows the miss>
Repeat: <yes, with the earlier time it happened | no | unknown>
Suggested layer: <one layer from the correction lens guide, with one reason | unknown>
```

Keep each field to one or two lines. The issue reader works without the session's transcript, so each field names the file, message, or link it rests on.

## Playbooks

| Mode | What follows the brief |
|---|---|
| Post, the default | Steps 3 to 6 of Post the issue. No control and no pull request. |
| `fix`, typed by the user | Post the issue, then read [`playbooks/fix.md`](playbooks/fix.md) and run its steps from step 2. |

## Layout

| File | What it holds |
|---|---|
| `SKILL.md` | Posting the issue, the listing, the brief, and the playbook index |
| `playbooks/fix.md` | The steps that land one correction as a control and a pull request, on a typed `/correction fix` |
| `scripts/correction_filing.py` | Picks the corrected repository or the fallback inbox, then posts, dedupes, and lists the correction issues |
| `scripts/correction_filing_constants/config/constants.py` | Issue shape, label, fallback messages, and redaction patterns |
| `scripts/test_correction_filing.py` | Behavior tests with a stand-in `gh` and a stand-in post lint |
| `references/filing.md` | Repository choice, fallback inbox, issue shape, dedupe, and commands |
