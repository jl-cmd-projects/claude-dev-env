# Comment preservation

[Back to the index](../CODE_RULES.md#comment-preservation)

I keep comments attached to untouched code. When I change the code a comment describes, I remove that comment and put its meaning in names and structure.

## Checks

- check_comment_changes

## When it fires

The code-rules enforcer runs check_comment_changes on changed *.py, *.js, *.mjs, and *.ts lines during staged validation.

The rule applies to production and tests. Existing comments outside the changed code stay in place. Keep cleanup within the requested task.

## Proving it

Run the named pytest node or command with the described input. A breach produces a rule finding; advisory checks write to stderr.

- check_comment_changes: a new JavaScript comment on a changed line; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_javascript_comments.py::test_check_comment_changes_reports_javascript_comment_line` reports a named violation.

## Gotchas

A keep marker needs a configured prefix. A changed directive or task marker is removed. Docstrings remain allowed.
