from hooks_constants import piped_pytest_blocker_constants as constants


def test_pytest_programs_and_interpreters_cover_supported_invocations() -> None:
    assert {"pytest", "pytest.exe", "py.test"} <= constants.ALL_PYTEST_PROGRAM_BASENAMES
    assert constants.PYTHON_INTERPRETER_BASENAME_PATTERN.fullmatch("python3.12.exe")
    assert (constants.MODULE_RUN_FLAG, constants.PYTEST_MODULE_NAME) == ("-m", "pytest")


def test_pipe_and_wrapper_tokens_preserve_command_boundaries() -> None:
    assert {"|", "|&"} <= constants.ALL_PIPE_OPERATOR_TOKENS
    assert ";;" in constants.ALL_SEGMENT_RESET_OPERATOR_TOKENS
    assert "-u" in constants.ALL_WRAPPER_OPTION_GRAMMARS_BY_NAME["sudo"].all_value_taking_options
    assert constants.ALL_WRAPPER_OPTION_GRAMMARS_BY_NAME["timeout"].leading_operand_count == 1


def test_shell_keywords_and_builtins_step_to_the_command_they_run() -> None:
    assert {"if", "then", "do", "!"} <= constants.ALL_SHELL_KEYWORDS_BEFORE_A_COMMAND
    for each_keyword in constants.ALL_SHELL_KEYWORDS_BEFORE_A_COMMAND:
        assert (
            constants.ALL_WRAPPER_OPTION_GRAMMARS_BY_NAME[each_keyword]
            == constants.SHELL_KEYWORD_OPTION_GRAMMAR
        )
    assert "-a" in constants.ALL_WRAPPER_OPTION_GRAMMARS_BY_NAME["exec"].all_value_taking_options
    assert "-p" in constants.ALL_WRAPPER_OPTION_GRAMMARS_BY_NAME["command"].all_flag_options
