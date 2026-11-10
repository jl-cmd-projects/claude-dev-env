"""Choose the Codex account a review runs on from the account broker's answer.

::

    broker exit 0, tier normal, home "C:/profiles/codex-1"  ->  Path("C:/profiles/codex-1")
    broker exit 3 (wait), or a tier other than normal       ->  CodexAccountUnavailable
    broker exit 2, no JSON, no home                         ->  CodexAccountUnavailable

The broker answers only with an account on a listed paid plan, never a free,
unknown, or unlisted plan, so the home it names is the only account a review may
use. A home already set in ``CODEX_HOME`` goes through the same broker check,
which refuses it when its plan is free, unknown, or not a listed paid plan, or its
meters are unread. A paid plan passes whatever its room.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from codex_review_scripts_constants.account_constants import (
    ACCOUNT_BROKER_CHOOSE_COMMAND,
    ACCOUNT_BROKER_CODEX_PRODUCT,
    ACCOUNT_BROKER_HOME_FLAG,
    ACCOUNT_BROKER_PRODUCT_FLAG,
    ALL_ACCOUNT_BROKER_RELATIVE_PARTS,
    ALL_ACCOUNT_BROKER_REQUIRE_TIER_ARGUMENTS,
    ALL_BROKER_ACCEPTED_EXIT_CODES,
    ALL_NORMAL_ONLY_TIERS,
    BROKER_DECISION_KEY,
    BROKER_EXIT_REASON_TEMPLATE,
    BROKER_HOME_KEY,
    BROKER_MALFORMED_REASON,
    BROKER_NO_HOME_REASON,
    BROKER_REASON_KEY,
    BROKER_TIER_KEY,
    BROKER_WAIT_EXIT_CODE,
    NO_ACCOUNT_EXIT_CODE,
    NO_ROOM_REASON_TEMPLATE,
    SHARED_ROOT_PARENT_INDEX,
)


class CodexAccountUnavailable(Exception):
    """No Codex account can run the review, so the review does not start.

    Attributes:
        exit_code: The broker's own exit code, or the no-account sentinel.
        reason: Plain-words cause for the caller's report.
    """

    def __init__(self, exit_code: int, reason: str) -> None:
        super().__init__(reason)
        self.exit_code = exit_code
        self.reason = reason


def account_broker_path() -> Path:
    """Return the account broker in the scripts directory beside the shared tree.

    ::

        ~/.claude/_shared/pr-loop/scripts  ->  ~/.claude/scripts/account_broker.py

    Returns:
        Path to ``account_broker.py``.
    """
    shared_root = Path(__file__).resolve().parents[SHARED_ROOT_PARENT_INDEX]
    return shared_root.joinpath(*ALL_ACCOUNT_BROKER_RELATIVE_PARTS)


def broker_choose_command() -> list[str]:
    """Return the command that asks the broker for a Codex account.

    Returns:
        Interpreter, broker path, and the ``choose --product codex --require-tier normal`` arguments.
    """
    return [
        sys.executable,
        str(account_broker_path()),
        ACCOUNT_BROKER_CHOOSE_COMMAND,
        ACCOUNT_BROKER_PRODUCT_FLAG,
        ACCOUNT_BROKER_CODEX_PRODUCT,
        *ALL_ACCOUNT_BROKER_REQUIRE_TIER_ARGUMENTS,
    ]


def broker_home_check_command(codex_home: str) -> list[str]:
    """Return the command that asks the broker whether one Codex home may run.

    Args:
        codex_home: The Codex home path already set for the review.

    Returns:
        Interpreter, broker path, and the ``choose --product codex --home`` arguments.
    """
    return [
        sys.executable,
        str(account_broker_path()),
        ACCOUNT_BROKER_CHOOSE_COMMAND,
        ACCOUNT_BROKER_PRODUCT_FLAG,
        ACCOUNT_BROKER_CODEX_PRODUCT,
        ACCOUNT_BROKER_HOME_FLAG,
        codex_home,
    ]


def _decision_fields(answer_text: str) -> dict[str, object]:
    try:
        answer = json.loads(answer_text)
    except (TypeError, json.JSONDecodeError) as error:
        raise CodexAccountUnavailable(
            NO_ACCOUNT_EXIT_CODE, BROKER_MALFORMED_REASON
        ) from error
    decision = answer.get(BROKER_DECISION_KEY) if isinstance(answer, dict) else None
    if not isinstance(decision, dict):
        raise CodexAccountUnavailable(NO_ACCOUNT_EXIT_CODE, BROKER_MALFORMED_REASON)
    return decision


def codex_home_from_broker_answer(
    exit_code: int,
    answer_text: str,
    all_accepted_tiers: tuple[str, ...] = ALL_NORMAL_ONLY_TIERS,
) -> Path:
    """Read the Codex home a review may run on from the broker's answer.

    ::

        exit 0, {"decision": {"tier": "normal", "home": "C:/p/codex-1"}}  ->  Path("C:/p/codex-1")
        exit 3, {"decision": {"tier": "wait", "reason": "..."}}           ->  refused
        exit 0, {"decision": {"tier": "luna", "home": "C:/p/codex-1"}}    ->  refused

    With no home pinned, a review runs only on the ``normal`` tier, as the
    convergence gate and the Astra advisor do. ``luna`` and ``wait`` mean no
    account has room for one. A home pinned in ``CODEX_HOME`` goes through the
    broker too. The broker refuses it unless its plan is paid and its meters can
    be read, and it answers ``wait`` while a saved spent mark holds the roster
    account that has that home. A home the roster does not list reads as an
    account named for its folder, so a mark saved for the no-roster default
    account, named ``default``, does not hold ``--home <that home>`` unless the
    folder of that home is also named ``default``. A home that passes runs at any
    tier, so the caller passes every tier the broker may run, and launches on the
    home the answer names. The Astra advisor treats a pinned home the same way.

    Args:
        exit_code: Exit code of ``account_broker.py choose --product codex``.
        answer_text: Standard output of that command.
        all_accepted_tiers: Tiers the answer may name, ``normal`` only by default.

    Returns:
        The Codex home to set as ``CODEX_HOME`` for the review.

    Raises:
        CodexAccountUnavailable: The broker exited with a code other than 0 or
            3, printed text that is not JSON or JSON with no ``decision``
            object, waited, chose a tier outside ``all_accepted_tiers``, or
            named no home.
    """
    if exit_code not in ALL_BROKER_ACCEPTED_EXIT_CODES:
        raise CodexAccountUnavailable(
            exit_code, BROKER_EXIT_REASON_TEMPLATE.format(exit_code=exit_code)
        )
    decision = _decision_fields(answer_text)
    if (
        exit_code == BROKER_WAIT_EXIT_CODE
        or decision.get(BROKER_TIER_KEY) not in all_accepted_tiers
    ):
        reason = decision.get(BROKER_REASON_KEY)
        raise CodexAccountUnavailable(
            NO_ACCOUNT_EXIT_CODE,
            NO_ROOM_REASON_TEMPLATE.format(
                reason=reason if isinstance(reason, str) else ""
            ),
        )
    chosen_home = decision.get(BROKER_HOME_KEY)
    if not isinstance(chosen_home, str) or not chosen_home:
        raise CodexAccountUnavailable(NO_ACCOUNT_EXIT_CODE, BROKER_NO_HOME_REASON)
    return Path(chosen_home)
