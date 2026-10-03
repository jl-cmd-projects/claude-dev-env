# Naming and types

[Back to the index](../CODE_RULES.md#5-no-abbreviations)

I name identifiers for their role and type the boundary of each public function.

## Checks

- check_known_pytest_fixture_annotations
- check_parameter_annotations
- check_return_annotations
- check_unused_known_pytest_fixture_parameters
- check_banned_identifiers
- check_banned_noun_word_boundary
- check_banned_prefixes
- check_boolean_naming
- check_js_banned_identifiers
- check_js_boolean_naming
- check_collection_prefix
- check_loop_variable_naming
- check_polarity_name_contradiction
- check_referenced_underscore_loop_variable
- check_stuttering_collection_prefix
- check_boundary_types
- check_type_escape_hatches
- check_typed_dict_encode_decode

## When it fires

The code-rules enforcer checks names in changed *.py, *.js, *.mjs, and *.ts declarations. Type and pytest fixture checks use test_*.py, *_test.py, and tests/ paths.

Known pytest fixture parameters are tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, capfd, caplog, request, and tmp_path_factory with their documented injected types. A collectable test drops a known fixture parameter it never reads, augments, or deletes. Reads inside nested functions and comprehensions count. Ordinary test parameters remain exempt. For typed data, keep _encode_* and _decode_* companions in the same module. The banned identifiers include ctx, cfg, msg, btn, idx, cnt, tmp, elem, and val. Public function names avoid handle_, process_, manage_, and do_.

## Proving it

Run the named pytest node or command with the described input. A breach produces a rule finding; advisory checks write to stderr.

- check_known_pytest_fixture_annotations: an untyped tmp_path parameter in a test; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_annotations.py::test_should_flag_unannotated_known_fixture_in_test_file` reports a named violation.
- check_parameter_annotations: a public parameter without an annotation; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_annotations.py::test_should_flag_parameter_without_annotation` reports a named violation.
- check_return_annotations: a function without a return annotation; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_annotations.py::test_should_flag_function_without_return_annotation` reports a named violation.
- check_unused_known_pytest_fixture_parameters: a test declaring tmp_path and never reading it; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_annotations.py::test_should_flag_unused_known_fixture_parameter_in_test_file` reports a named violation.
- check_banned_identifiers: a changed ctx binding; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_banned_identifier.py` reports a named violation.
- check_banned_noun_word_boundary: a public function binding a banned noun; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_banned_noun_word.py` reports a named violation.
- check_banned_prefixes: a function named handle_event; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_banned_prefixes.py::test_should_flag_handle_prefixed_function` reports a named violation.
- check_boolean_naming: a boolean assignment named enabled; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_naming_pattern.py::test_should_flag_boolean_assignment_without_is_prefix` reports a named violation.
- check_js_banned_identifiers: a JavaScript declaration named ctx; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_naming_pattern.py` reports a named violation.
- check_js_boolean_naming: a boolean JavaScript declaration named enabled; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_naming_pattern.py` reports a named violation.
- check_collection_prefix: a list parameter named users; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_collection_prefix.py` reports a named violation.
- check_loop_variable_naming: a loop variable named user; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_split_naming.py::test_check_loop_variable_naming_flags_missing_each_prefix` reports a named violation.
- check_polarity_name_contradiction: an is_allowed binding assigned from is_forbidden; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_polarity_name_contradiction.py::test_should_flag_allowed_target_assigned_from_forbidden_callee` reports a named violation.
- check_referenced_underscore_loop_variable: a loop variable named _user that its body reads; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_referenced_underscore_loop.py::test_should_flag_referenced_underscore_loop_variable_in_conftest` reports a named violation.
- check_stuttering_collection_prefix: a collection named all_all_users; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_split_naming.py::test_stuttering_collection_prefix_flags_function_name_loop1_1` reports a named violation.
- check_boundary_types: Any as a direct parameter annotation; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_boundary_types.py::test_should_flag_any_as_direct_param_annotation` reports a named violation.
- check_type_escape_hatches: a cast call around a parameter; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_any_type_ignore.py::test_should_flag_any_parameter_annotation` reports a named violation.
- check_typed_dict_encode_decode: a TypedDict with no encode and decode companion; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_typed_dict_pairs.py::test_should_flag_typed_dict_without_encode_or_decode` reports a named violation.

## Gotchas

Known fixture names need an injected type even in test files. Fixture functions can request another fixture for setup order. Local nested helpers are outside the unused-fixture check.
