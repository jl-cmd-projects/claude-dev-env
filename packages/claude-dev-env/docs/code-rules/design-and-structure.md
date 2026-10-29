# Design and structure

[Back to the index](../CODE_RULES.md#7-right-sized-engineering)

I keep components cohesive and remove code whose entry-point path disappeared.

## Checks

- check_function_length
- check_blast_radius_declared
- check_duplicate_function_body_across_files
- check_unused_optional_parameters
- check_orphan_css_classes
- check_bare_except
- check_test_branching_in_production
- check_stub_implementations
- check_thin_wrapper_files

## When it fires

The code-rules enforcer checks structure, exception boundaries, and length in changed *.py files. It checks class names in changed *.css and component files. File-length advisories run at 400 and 1000 lines.

A member loop catches a declared ItemBlocked type inside the loop, records the member and reason, then continues. Escalations re-raise first, so a RunFatal passes through, and `except Exception` triggers the rule. The run report names each parked member. [Failure scope](../../rules/failure-blast-radius.md) gives the boundary shape. To remove orphaned code, run Serena find_referencing_symbols and search text for getattr and entry-point strings. Trace each reference to a live CLI command, route, public API, or test. Remove a dead self-referential cluster together. Keep uncertain symbols and surface the ambiguity. Follow the [dead-code procedure](../references/dead-code-elimination.md). Keep a component's state, modals, overlays, and toasts with that component. Re-exports belong in __init__.py. Update call sites when changing a symbol.

## Proving it

Run the named pytest node or command with the described input. A breach produces a rule finding; advisory checks write to stderr.

- check_function_length: a function at the blocking length threshold; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_function_length.py::test_should_block_at_sixty_lines` reports a blocking violation naming the function.
- check_blast_radius_declared: a raise inside a loop body with no declared handler; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_blast_radius.py::test_should_report_a_loop_raise_with_pending_blast_radius_declaration` reports an advisory. A RunFatal raise or an ItemBlocked raise inside a loop passes.
- check_duplicate_function_body_across_files: one function body copied into a sibling module; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_duplicate_body.py::test_should_flag_function_copied_from_sibling` reports a named violation.
- check_unused_optional_parameters: an optional parameter with one fixed value at every call site; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_split_optional_params.py::test_should_flag_optional_param_never_varied_in_file` reports a named violation.
- check_orphan_css_classes: a markup class with no matching CSS selector; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_orphan_css_class.py::test_should_flag_class_with_no_matching_selector` reports a named violation.
- check_bare_except: a bare except clause; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_bare_except.py::test_should_flag_bare_except` reports a named violation.
- check_test_branching_in_production: a production branch on an environment testing flag; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_test_branching.py::test_should_flag_os_environ_get_testing_branch` reports a named violation.
- check_stub_implementations: a public function with a pass-only body; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_stub_implementations.py::test_should_flag_pass_only_function` reports a named violation.
- check_thin_wrapper_files: a module containing only imports and __all__; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_thin_wrapper_files.py::test_should_flag_thin_wrapper_with_imports_and_all` reports a named violation.

## Gotchas

A length advisory asks for a cohesion review. Reflective dispatch, public APIs, and plugin hooks can hide references. Surface uncertain liveness and keep the code.
