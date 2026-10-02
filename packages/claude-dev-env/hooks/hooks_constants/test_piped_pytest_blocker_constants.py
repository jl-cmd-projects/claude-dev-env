from hooks_constants import piped_pytest_blocker_constants as constants


def test_pipe_operators_cover_both_shell_spellings() -> None:
    assert constants.ALL_PIPE_OPERATOR_TOKENS == frozenset({"|", "|&"})
    assert constants.ALL_PIPE_OPERATOR_TOKENS.isdisjoint(
        constants.ALL_SEGMENT_RESET_OPERATOR_TOKENS
    )


def test_heredoc_opener_distinguishes_here_strings() -> None:
    opener = constants.HEREDOC_OPENER_PATTERN
    match = opener.search("cat <<'EOF'")
    assert match is not None
    assert match.group(constants.HEREDOC_TERMINATOR_GROUP) == "EOF"
    assert opener.search("cat <<<EOF") is None
