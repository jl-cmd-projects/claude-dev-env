# TDD and proof

[Back to the index](../CODE_RULES.md#8-tdd-process)

I write a failing behavior test, make it pass, then refactor when the change benefits from cleanup.

## Checks

- check_e2e_test_naming
- check_public_function_missing_paired_test
- check_test_file_omits_module_public_function
- check_constant_equality_tests
- check_existence_check_tests
- check_flag_gated_scenario_test_naming
- check_skip_decorators_in_tests
- check_stale_test_name_target
- check_vacuous_cleanup_assertion_tests
- check_tests_use_isolated_filesystem_paths
- check_dead_test_module_constant
- check_unused_test_helper_parameter

## When it fires

The code-rules enforcer runs test assertion, paired-test, isolation, and layout checks on test_*.py, *_test.py, and tests/ paths. Paired-test checks also read linked *.py production modules.

The TDD loop is the default for bug fixes and new behavior. A prototype may precede its tests and adds them before review readiness. Hook lint does not check the order. A bug fix includes a reproducing test. Proof can be a named test, run, screenshot, or measurement.

## Proving it

Run the named pytest node or command with the described input. A breach produces a rule finding; advisory checks write to stderr.

- check_e2e_test_naming: an end-to-end test with an unmarked name; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_dot_test_pattern.py` reports a named violation.
- check_public_function_missing_paired_test: a new public function absent from its established suite; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_paired_test.py::test_flags_public_function_absent_from_established_suite` reports a named violation.
- check_test_file_omits_module_public_function: an established test module omitting a public function; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_paired_test.py::test_flags_module_public_function_when_test_suite_omits_it` reports a named violation.
- check_constant_equality_tests: a test asserting a constant equals its literal; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_constant_equality.py::test_should_flag_test_asserting_constant_equals_literal` reports a named violation.
- check_existence_check_tests: a test asserting only that a function exists; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_existence_checks.py::test_should_flag_test_with_only_callable_assertion` reports a named violation.
- check_flag_gated_scenario_test_naming: a flag-gated scenario whose name omits its flag; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_split_test_assertions.py::test_should_advise_when_scenario_test_omits_flag_its_siblings_patch` reports a stderr advisory.
- check_skip_decorators_in_tests: a skipped pytest test function; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_skip_decorators.py::test_should_flag_pytest_mark_skip_on_test_function` reports a named violation.
- check_stale_test_name_target: a test name still naming a removed function; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_stale_test_name.py::test_flags_renamed_away_target_in_test_name` reports a named violation.
- check_vacuous_cleanup_assertion_tests: a cleanup test with no created temporary file; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_vacuous_cleanup_assertion.py::test_should_flag_glob_emptiness_cleanup_test_without_temp_creation` reports a named violation.
- check_tests_use_isolated_filesystem_paths: a test writing to a shared user-home path; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_tests_isolate_home_temp.py` reports a named violation.
- check_dead_test_module_constant: an unused private constant in a test module; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_test_layout.py` reports a named violation.
- check_unused_test_helper_parameter: a test helper parameter its body never reads; `python -m pytest packages/claude-dev-env/hooks/blocking/test_code_rules_enforcer_test_layout.py` reports a named violation.

## Gotchas

A cleanup test needs setup that creates something to clean. A renamed function needs updated test names. A pull request body names repeatable proof.
