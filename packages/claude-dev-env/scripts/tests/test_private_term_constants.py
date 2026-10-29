"""Behavior tests for the private-term digest sets."""

from __future__ import annotations

from dev_env_scripts_constants import private_term_constants


def test_should_scan_messages_for_every_digest_accepted_in_a_commit_identity() -> None:
    assert (
        private_term_constants.ALL_COMMIT_IDENTITY_ACCEPTED_DIGESTS
        <= private_term_constants.ALL_PRIVATE_TERM_DIGESTS
    )


def test_should_accept_the_agent_account_email_in_a_commit_identity() -> None:
    assert (
        private_term_constants.AGENT_ACCOUNT_EMAIL_DIGEST
        in private_term_constants.ALL_COMMIT_IDENTITY_ACCEPTED_DIGESTS
    )
