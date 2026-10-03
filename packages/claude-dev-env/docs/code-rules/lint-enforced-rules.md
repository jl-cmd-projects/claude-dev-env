# Lint-enforced rules

[Back to the index](../CODE_RULES.md#-lint-enforced-rules)

I use the staged enforcer findings to locate the breached pattern and the relevant fixture.

## Checks

- check_class_docstring_names_public_methods
- check_docstring_args_match_signature
- check_docstring_documents_unreferenced_parameter
- check_docstring_format
- check_docstring_names_undefined_constant
- check_docstring_prose_wall_without_illustration
- check_docstring_runon_sentence
- check_module_docstring_names_public_checks
- check_module_docstring_scope_omits_data_schema_constants
- check_imports_at_top
- check_js_bare_flag_return_directive
- check_js_resume_task_enumeration_coverage
- check_js_returns_object_schemaless_branch
- check_js_sibling_return_object_key_drift
- check_library_print
- check_logging_adjacent_string_literals
- check_logging_fstrings
- check_naive_datetime_construction
- check_windows_api_none

## When it fires

The code-rules enforcer runs on changed *.py, *.js, *.mjs, and *.ts files. Docstring, import, logging, and datetime checks use *.py. JavaScript return checks use *.js and *.mjs.

The roster covers imports at top, logging format arguments, hardcoded home paths, guarded path insertion, bare and broad exception handlers, docstring formats and contents, JavaScript return objects, and platform calls. Public functions with parameters use Google-style Args entries that match the signature. Long prose in a docstring calls for an illustration. Command classifiers anchor a multiword expression at the command start or tokenize its first word.

## Proving it

Run the named pytest node or command with the described input. A breach produces a rule finding; advisory checks write to stderr.

- check_class_docstring_names_public_methods: a class summary omitting its public methods; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_class_docstring_methods.py::test_should_flag_single_line_docstring_omitting_two_public_methods` reports a named violation.
- check_docstring_args_match_signature: an Args entry absent from the signature; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_docstring_args_signature.py::test_should_flag_documented_arg_not_in_signature` reports a named violation.
- check_docstring_documents_unreferenced_parameter: a documented parameter unused in the body; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_docstring_unreferenced_param.py` reports a named violation.
- check_docstring_format: a public function with parameters and no Args section; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_docstring_format.py::test_should_flag_public_function_with_params_missing_args_section` reports a named violation.
- check_docstring_names_undefined_constant: a docstring naming an undefined constant; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_docstring_undefined_constant.py::test_flags_docstring_naming_constant_the_module_never_defines` reports a named violation.
- check_docstring_prose_wall_without_illustration: a prose-wall docstring with no example; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_docstring_prose_wall_illustration.py::test_should_flag_prose_wall_with_no_illustration` reports a named violation.
- check_docstring_runon_sentence: a long run-on docstring sentence; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_docstring_runon_sentence.py::test_should_flag_run_lifecycle_module_docstring_wall` reports a named violation.
- check_module_docstring_names_public_checks: a module summary omitting a public check; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_module_docstring_roster.py::test_should_flag_module_docstring_omitting_a_public_check` reports a named violation.
- check_module_docstring_scope_omits_data_schema_constants: a module summary listing schema constants as behavior; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_module_docstring_data_schema_scope.py` reports a named violation.
- check_imports_at_top: an ordinary import inside a function; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_type_checking_scope.py::test_should_allow_import_inside_if_type_checking_block` reports a named violation.
- check_js_bare_flag_return_directive: a JavaScript return directive with an unexplained bare flag; `python -m pytest packages/claude-dev-env/hooks/blocking` reports a named violation.
- check_js_resume_task_enumeration_coverage: a resume task branch missing an enumerated state; `python -m pytest packages/claude-dev-env/hooks/blocking` reports a named violation.
- check_js_returns_object_schemaless_branch: sibling JavaScript return paths with an ad hoc object; `python -m pytest packages/claude-dev-env/hooks/blocking` reports a named violation.
- check_js_sibling_return_object_key_drift: sibling return objects with different keys; `python -m pytest packages/claude-dev-env/hooks/blocking` reports a named violation.
- check_library_print: a print call in library code; `python -m pytest packages/claude-dev-env/hooks/blocking` reports a named violation.
- check_logging_adjacent_string_literals: adjacent string literals in a logger call; `python -m pytest packages/claude-dev-env/hooks/blocking` reports a named violation.
- check_logging_fstrings: an f-string passed to logger.info; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_logger_fstring.py::test_should_flag_logger_info_fstring` reports a named violation.
- check_naive_datetime_construction: datetime.fromtimestamp without a timezone; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_naive_datetime.py::test_flags_fromtimestamp_without_timezone` reports a named violation.
- check_windows_api_none: a Windows API call passed None for a required argument; `python -m pytest packages/claude-dev-env/hooks/blocking` reports a named violation.

## Gotchas

Some checks report only changed lines. Import order and unused imports belong to ruff F401 and I001. Advisory findings write to stderr.
