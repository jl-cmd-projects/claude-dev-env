# Core principles and config

[Back to the index](../CODE_RULES.md#core-principles)

I search for shared code and configuration before adding a constant or repeating construction logic.

## Checks

- check_config_duplicate_path_anchor
- check_constants_outside_config
- check_constants_outside_config_advisory
- check_fstring_structural_literals
- check_magic_values
- check_duplicated_format_patterns
- check_hardcoded_user_paths
- check_sys_path_insert_deduplication_guard
- check_inline_literal_collections
- check_inline_tuple_string_magic
- check_join_separator_string_magic
- check_string_literal_magic
- check_whitespace_indentation_magic

## When it fires

The code-rules enforcer runs constant, path, magic-value, and duplicate-format checks on changed *.py files. String and collection checks inspect production function bodies in *.py files.

Search config for the exact value and a semantic match. Add timing to config/timing.py, ports and thresholds to config/constants.py, and selectors to config/selectors.py. Keep construction and formatting with the owner of the data. Constants outside config are exempt in migrations, workflow registries, and test files. Workflow registry matching uses path substrings /workflow/, _tab.py, /states.py, and /modules.py. The test-file patterns include test_, _test., .spec., conftest, and /tests/.

## Proving it

Run the named pytest node or command with the described input. A breach produces a rule finding; advisory checks write to stderr.

- check_config_duplicate_path_anchor: two config constants pointing at the same path; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_config_duplicate_path_anchor.py::test_should_flag_reanchored_base_already_built_by_sibling` reports a named violation.
- check_constants_outside_config: UPPER_SNAKE = 3 in a production module; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_config_path.py::test_should_produce_blocking_for_module_level_upper_snake_outside_config` reports a named violation.
- check_constants_outside_config_advisory: a function-local UPPER_SNAKE constant; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_split_constants_config.py::test_advisory_should_flag_annotated_function_body_constant` reports a stderr advisory.
- check_fstring_structural_literals: an f-string that embeds a URL path fragment; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_fstring_scan.py::test_should_flag_fstring_with_url_path` reports a named violation.
- check_magic_values: a production function comparing a value with 2; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_magic_allowlist.py::test_check_magic_values_should_flag_literal_two_in_function_body` reports a named violation.
- check_duplicated_format_patterns: the same f-string skeleton at three call sites; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_split_optional_params.py::test_should_advise_when_fstring_skeleton_appears_three_or_more_times` reports a stderr advisory.
- check_hardcoded_user_paths: a fixed user-home path in source; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_hardcoded_user_path.py::test_should_flag_windows_user_path_with_forward_slashes` reports a named violation.
- check_sys_path_insert_deduplication_guard: an unguarded module-level sys.path.insert call; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_sys_path_insert.py::test_should_flag_unguarded_module_level_insert` reports a named violation.
- check_inline_literal_collections: a three-string set inside a function; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_split_string_magic.py::test_check_inline_literal_collections_flags_three_string_set_in_function` reports a named violation.
- check_inline_tuple_string_magic: an inline tuple of two snake-case labels; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_inline_tuple_string_magic.py::test_should_flag_inline_snake_case_tuple_pair_inside_function` reports a named violation.
- check_join_separator_string_magic: a literal delimiter passed to join in a function; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_join_separator_magic.py::test_should_flag_literal_delimiter_join_separator_in_function_body` reports a named violation.
- check_string_literal_magic: an environment-variable name literal in a function; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_string_magic.py::test_should_flag_env_var_name_string_in_function_body` reports a named violation.
- check_whitespace_indentation_magic: a repeated literal indentation string in a function; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_whitespace_indentation_magic.py` reports a named violation.

## Gotchas

Migration paths, config files, workflow registries, and tests have distinct constant exemptions. Each workflow substring matches independently.
