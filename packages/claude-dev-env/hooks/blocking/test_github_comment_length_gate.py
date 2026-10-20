import github_comment_length_gate

LONG_COMMENT = " ".join(
    "Sentence number one of a long comment that keeps going." for _ in range(50)
)
SHORT_COMMENT = "Fixed the cap check. The test now covers it. Checks pass."


def test_long_mcp_comment_is_denied() -> None:
    all_texts = github_comment_length_gate.comment_body_texts(
        "mcp__github__add_issue_comment", {"body": LONG_COMMENT}
    )
    assert github_comment_length_gate.comment_violation(all_texts[0]) is not None


def test_short_comment_passes() -> None:
    assert github_comment_length_gate.comment_violation(SHORT_COMMENT) is None


def test_code_and_details_blocks_carry_no_words() -> None:
    comment_text = (
        SHORT_COMMENT
        + "\n```\n" + LONG_COMMENT + "\n```\n"
        + "<details><summary>Log</summary>\n" + LONG_COMMENT + "\n</details>"
    )
    assert github_comment_length_gate.comment_violation(comment_text) is None


def test_gh_comment_command_body_is_checked() -> None:
    command = f'gh pr comment 12 --body "{LONG_COMMENT}"'
    assert github_comment_length_gate.comment_body_texts("Bash", {"command": command}) == [LONG_COMMENT]


def test_gh_pr_create_body_is_not_checked() -> None:
    command = f'gh pr create --body "{LONG_COMMENT}"'
    assert github_comment_length_gate.comment_body_texts("Bash", {"command": command}) == []
