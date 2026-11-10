"""Choose the Codex account a live review evaluation runs on.

::

    CODEX_HOME already set, broker accepts  ->  environment with CODEX_HOME the home the broker answers
    CODEX_HOME already set, broker refuses  ->  CodexAccountUnavailable
    broker exit 0, tier normal, home "H"    ->  environment with CODEX_HOME "H"
    broker exit 3, other tier, any failure  ->  CodexAccountUnavailable

The broker never answers with a free-plan or unknown-plan account, so the home
it names is the only account a model run may use. A home already set in
``CODEX_HOME`` goes through the same broker check, and the run launches on the
home the broker answers, the trimmed absolute folder it judged.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from review_eval_support.config.constants import (
    ACCOUNT_BROKER_PACKAGE_PARENT_INDEX,
    ACCOUNT_BROKER_TIMEOUT_SECONDS,
    ALL_ACCOUNT_BROKER_ARGUMENTS,
    ALL_ACCOUNT_BROKER_HOME_CHECK_ARGUMENTS,
    ALL_ACCOUNT_BROKER_RELATIVE_PARTS,
    ALL_BROKER_ACCEPTED_EXIT_CODES,
    ALL_NORMAL_ONLY_TIERS,
    ALL_RUN_TIERS,
    BROKER_DECISION_KEY,
    BROKER_EXIT_REASON_TEMPLATE,
    BROKER_HOME_KEY,
    BROKER_MALFORMED_REASON,
    BROKER_MISSING_REASON,
    BROKER_NO_HOME_REASON,
    BROKER_NOT_RUN_REASON,
    BROKER_REASON_KEY,
    BROKER_TIER_KEY,
    BROKER_WAIT_EXIT_CODE,
    CODEX_HOME_VARIABLE,
    NO_ROOM_REASON_TEMPLATE,
    SUITE_ROOT,
)


class CodexAccountUnavailable(Exception):
    """No Codex account can run the evaluation, so no model call starts."""


def default_broker_candidates() -> tuple[Path, ...]:
    """Return the broker script paths to try, in order.

    Returns:
        The scripts directory of the package that holds this suite, then its
        ``.claude`` copy.
    """
    package_root = SUITE_ROOT.parents[ACCOUNT_BROKER_PACKAGE_PARENT_INDEX]
    return tuple(
        package_root.joinpath(*each_parts)
        for each_parts in ALL_ACCOUNT_BROKER_RELATIVE_PARTS
    )


def broker_script(all_candidates: tuple[Path, ...]) -> Path:
    """Return the first account broker script that exists.

    Args:
        all_candidates: Paths to try in order.

    Returns:
        Path to ``account_broker.py``.

    Raises:
        CodexAccountUnavailable: No candidate is a file.
    """
    for each_candidate in all_candidates:
        if each_candidate.is_file():
            return each_candidate
    raise CodexAccountUnavailable(BROKER_MISSING_REASON)


def _broker_answer(all_broker_arguments: tuple[str, ...]) -> tuple[int, str]:
    command = [
        sys.executable,
        str(broker_script(default_broker_candidates())),
        *all_broker_arguments,
    ]
    try:
        completed_call = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=ACCOUNT_BROKER_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise CodexAccountUnavailable(BROKER_NOT_RUN_REASON) from error
    return completed_call.returncode, completed_call.stdout


def _decision(answer_text: str) -> dict:
    try:
        answer = json.loads(answer_text)
    except (TypeError, json.JSONDecodeError) as error:
        raise CodexAccountUnavailable(BROKER_MALFORMED_REASON) from error
    decision = answer.get(BROKER_DECISION_KEY) if isinstance(answer, dict) else None
    if not isinstance(decision, dict):
        raise CodexAccountUnavailable(BROKER_MALFORMED_REASON)
    return decision


def _home_from_answer(
    exit_code: int,
    answer_text: str,
    all_accepted_tiers: tuple[str, ...],
) -> Path:
    if exit_code not in ALL_BROKER_ACCEPTED_EXIT_CODES:
        raise CodexAccountUnavailable(
            BROKER_EXIT_REASON_TEMPLATE.format(exit_code=exit_code)
        )
    decision = _decision(answer_text)
    if (
        exit_code == BROKER_WAIT_EXIT_CODE
        or decision.get(BROKER_TIER_KEY) not in all_accepted_tiers
    ):
        reason = decision.get(BROKER_REASON_KEY)
        raise CodexAccountUnavailable(
            NO_ROOM_REASON_TEMPLATE.format(
                reason=reason if isinstance(reason, str) else ""
            )
        )
    chosen_home = decision.get(BROKER_HOME_KEY)
    if not isinstance(chosen_home, str) or not chosen_home:
        raise CodexAccountUnavailable(BROKER_NO_HOME_REASON)
    return Path(chosen_home)


def codex_environment() -> dict[str, str]:
    """Return the environment a model run uses, with the broker's Codex home.

    ::

        CODEX_HOME " H "              ->  copy with CODEX_HOME set to the home the broker answers for "H"
        CODEX_HOME unset or blank     ->  copy with CODEX_HOME set to the broker's home

    Returns:
        Environment for the ``codex exec`` child process.

    Raises:
        CodexAccountUnavailable: The broker did not name a Codex home with room.
    """
    exported_home = os.environ.get(CODEX_HOME_VARIABLE, "").strip()
    if exported_home:
        judged_home = _home_from_answer(
            *_broker_answer((*ALL_ACCOUNT_BROKER_HOME_CHECK_ARGUMENTS, exported_home)),
            all_accepted_tiers=ALL_RUN_TIERS,
        )
        return {**os.environ, CODEX_HOME_VARIABLE: str(judged_home)}
    chosen_home = _home_from_answer(
        *_broker_answer(ALL_ACCOUNT_BROKER_ARGUMENTS),
        all_accepted_tiers=ALL_NORMAL_ONLY_TIERS,
    )
    return {**os.environ, CODEX_HOME_VARIABLE: str(chosen_home)}
