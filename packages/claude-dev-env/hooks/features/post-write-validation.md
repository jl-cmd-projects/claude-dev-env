# Post-write validation

This family checks a completed Write, Edit or MultiEdit call, formats eligible new source files, and runs an opted-in repository's lint on the edited file. The agent receives a combined block decision if a hosted check blocks.

## Checks

- `validation/post_tool_use_dispatcher.py` runs the post-write roster in order and combines any block reasons.
- `workflow/auto_formatter.py` formats eligible untracked source files after a Write and never blocks the write.
- `advisory/edit_lint_context.py` runs the lint command a repository names in `.claude/edit-lint.json` on the edited file and adds its findings to the agent's context. It runs only for a repository whose origin `owner/repo` slug is listed in `CLAUDE_EDIT_LINT_REPOSITORIES`, comma-separated, and whose root sits inside `CLAUDE_PROJECT_DIR`, the folder the session's workspace trust covers. It never blocks and never edits the file.
- `advisory/instruction_file_write_warning.py` runs the instruction budget check on a written instruction file, or a file a launch file imports, in a repository that has `instruction-budget.json` at its root. It adds a note for each over-budget launch total the written file counts toward, named person, or link chain beyond the cap, and never blocks.

## When it fires

- `validation/post_tool_use_dispatcher.py` runs on `PostToolUse`, matcher `Write|Edit|MultiEdit`, timeout `180` seconds in `hooks.json`.
- `workflow/auto_formatter.py` runs inside that dispatcher on `PostToolUse`, matcher `Write|Edit|MultiEdit`, timeout `180` seconds, as named by `ALL_POST_HOSTED_HOOK_ENTRIES`. Its eligibility check accepts only a Write of an untracked source file.
- `advisory/edit_lint_context.py` runs inside that dispatcher after the formatter, so it lints the file as the formatter left it.
- `advisory/instruction_file_write_warning.py` runs on `PostToolUse`, matcher `Write|Edit|MultiEdit`, timeout `30` seconds in `hooks.json`, as its own registration beside the dispatcher.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The formatter tests make disposable repositories.

- **Post-write dispatch.** Input is an Edit of plain text. Run `python -m pytest packages/claude-dev-env/hooks/validation/test_post_tool_use_dispatcher.py -q`. The adjacent test observes an allow result and the hosted formatter's selection.
- **Edit lint context.** Input is an Edit, Write or MultiEdit of a file in a disposable repository that lists a lint script. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_edit_lint_context.py -q`. The adjacent test observes the findings note for an opted-in repository and no output for a clean edit, an unlisted repository, an unlisted suffix, or a failed lint command.
- **Formatter eligibility.** Input is a Write of an untracked source file. Run `python -m pytest packages/claude-dev-env/hooks/workflow/test_auto_formatter.py -q`. The adjacent test observes formatting for eligible writes and no edit of a tracked file.
- **Instruction budget warning.** Input is a Write of an instruction file, or of a doc a launch file imports, in a repository with `instruction-budget.json`. Run `python -m pytest packages/claude-dev-env/hooks/advisory/test_instruction_file_write_warning.py -q`. The adjacent test observes a note for an over-budget or too-deep file, and no output for a clean file, a file outside the instruction set, a repository without the budget file, a skill file the launch total leaves out, or a read error during the check.

## Gotchas

- The current post-write roster contains `workflow/auto_formatter.py` and `advisory/edit_lint_context.py`. The dispatcher's docstring mentions other hosted work from an older roster, so use the roster for membership.
- The formatter can change the file after the original Write. A later hosted script would read the formatted file because the dispatcher preserves roster order.
- Formatter eligibility protects the hook tree and checks whether the file is tracked.
- The edit lint command's standard output is the findings. A repository's command prints nothing on a clean file and sends progress lines to stderr. A non-zero exit adds no note and writes one diagnostic line to stderr, so the command runs the lint in a mode that exits 0 when it reports findings.
