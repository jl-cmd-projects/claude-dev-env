# Post-write validation

This family checks a completed Write or Edit call and formats eligible new source files. The agent receives a combined block decision if a hosted check blocks.

## Checks

- `validation/post_tool_use_dispatcher.py` runs the post-write roster in order and combines any block reasons.
- `workflow/auto_formatter.py` formats eligible untracked source files after a Write and never blocks the write.

## When it fires

- `validation/post_tool_use_dispatcher.py` runs on `PostToolUse`, matcher `Write|Edit`, timeout `180` seconds in `hooks.json`.
- `workflow/auto_formatter.py` runs inside that dispatcher on `PostToolUse`, matcher `Write|Edit`, timeout `180` seconds, as named by `ALL_POST_HOSTED_HOOK_ENTRIES`. Its eligibility check accepts only a Write of an untracked source file.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The formatter tests make disposable repositories.

- **Post-write dispatch.** Input is an Edit of plain text. Run `python -m pytest packages/claude-dev-env/hooks/validation/test_post_tool_use_dispatcher.py -q`. The adjacent test observes an allow result and the hosted formatter's selection.
- **Formatter eligibility.** Input is a Write of an untracked source file. Run `python -m pytest packages/claude-dev-env/hooks/workflow/test_auto_formatter.py -q`. The adjacent test observes formatting for eligible writes and no edit of a tracked file.

## Gotchas

- The current post-write roster contains only `workflow/auto_formatter.py`. The dispatcher's docstring mentions other hosted work from an older roster, so use the roster for membership.
- The formatter can change the file after the original Write. A later hosted script would read the formatted file because the dispatcher preserves roster order.
- Formatter eligibility protects the hook tree and checks whether the file is tracked.
