# Enforcement surfaces

[Back to the index](../CODE_RULES.md#11-enforcement-surfaces)

I choose a check's lane from its scope and distinguish the roster from the findings shown to a caller.

## Checks

- check_unanchored_command_dispatch
- check_same_file_inline_duplicate_body
- check_zero_payload_function_alias

## When it fires

The blocking code-rules hook checks command dispatch in hooks/blocking/*.py and hook-infrastructure targets in hooks/**/*.py. Staged lint runs on changed *.py, *.js, *.mjs, and *.ts files; the full gate runs the wider roster.

Lint reports patterns; prompt context carries judgment about SRP, right-sized design, research on ambiguous intent, BDD discovery, and docstring prose. Audit rubrics A to Q cover cross-file concerns. Rules with pending checks live in rules/*.md and name their promotion path. Category O6 audits whether [docstring enumerations](../../rules/docstring-prose-matches-implementation.md) match behavior. Category O9 audits [illustrative docstrings](../../rules/plain-illustrative-docstrings.md). A summary line, a :: example or doctest, and short prose support that check. Validation uses three axes: EDIT_LANE_PHASE or FULL_GATE_PHASE chooses the roster; target classification narrows that roster; defer_scope_to_caller and changed lines filter findings. validate_content_for_phase requires an explicit phase keyword. validation_phase_constants.py owns the phase names and both roster sets. A check reading another file runs on the full gate; other checks run on both lanes. Hook-infrastructure edit targets run check_same_file_inline_duplicate_body, check_zero_payload_function_alias, and check_unanchored_command_dispatch. The full gate runs its complete roster. The timing harness uses an unchanged Write payload to time dispatch; use Edit to time checks. The hook denial log records test denials. run_all_validators.py stages a target under a temporary root and preserves its shortest exemption-bearing path tail. It skips pytest's own scratch directory when finding the project root.

## Proving it

Run the named pytest node or command with the described input. A breach produces a rule finding; advisory checks write to stderr.

- check_unanchored_command_dispatch: a command regex that matches a verb inside another command; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_command_dispatch.py::test_flags_unanchored_multi_word_command_pattern` reports a named violation.
- check_same_file_inline_duplicate_body: a helper body copied inline into a caller; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_same_file_inline_duplicate.py::test_should_flag_helper_whose_body_is_inlined_in_another_function` reports a named violation.
- check_zero_payload_function_alias: a pass-through alias forwarding the same arguments; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_zero_payload_alias.py::test_should_flag_pass_through_alias_forwarding_same_parameters` reports a named violation.

## Gotchas

Phase chooses the roster before target classification. Changed-line filtering only narrows reports. A Write payload with unchanged content can time dispatch without timing checks.
