"""Check visible closing prose for a reason to revisit the user's assignment once."""

from itertools import takewhile
from re import Match

from final_reply_gate import prose_paragraphs
from hooks_constants.open_tasks_stop_gate_constants import WORD_SEPARATOR
from hooks_constants.codex_continuation_constants import (
    ADDITIONAL_REQUEST,
    APPROVAL_SUBJECT,
    CANCELLED_REQUEST,
    CLAUSE_BREAK,
    CLOSING_PHRASE,
    CONTINUATION_REVIEW,
    LINE_SEPARATOR,
    MAX_REASON_SENTENCES,
    NEGATED_STATUS,
    ONLY_STATUS_REQUEST,
    PROTECTED_DECISION,
    QUOTED_EXAMPLE,
    REGISTERED_WAKE,
    RESOLVED_STATUS,
    SEPARATE_SUBJECT,
    STANDALONE_STOP,
    WAIT_SUBJECT,
)


def _unquoted(text: str) -> list[str]:
    return [QUOTED_EXAMPLE.sub(WORD_SEPARATOR, WORD_SEPARATOR.join(part.split())) for part in prose_paragraphs(text)]


def _warrants_review(match: Match[str], clause: str, explanation: str, has_question: bool) -> bool:
    if NEGATED_STATUS.search(clause[:match.start()]) or RESOLVED_STATUS.search(clause[match.end():]):
        return False
    protected = PROTECTED_DECISION.search(explanation)
    if APPROVAL_SUBJECT.search(clause) and (has_question or protected):
        return False
    is_wait = WAIT_SUBJECT.fullmatch(match.group())
    return not (is_wait and (REGISTERED_WAKE.search(explanation) or protected))


def continuation_review(reply: object, user_request: str, has_question: bool) -> str | None:
    """Return one review instruction for a possible unfinished outcome.

    Args:
        reply: Latest assistant message from Stop or SubagentStop.
        user_request: Current user turn, when available.
        has_question: Whether this turn opened an action-time decision.

    Returns:
        Review instruction when an unresolved statement warrants inspection.
    """
    if not isinstance(reply, str):
        return None
    request = WORD_SEPARATOR.join(_unquoted(user_request)).strip()
    if STANDALONE_STOP.fullmatch(request) or ONLY_STATUS_REQUEST.fullmatch(request):
        return None
    if CANCELLED_REQUEST.search(request) and not ADDITIONAL_REQUEST.search(request):
        return None
    all_clauses = [part.strip() for part in CLAUSE_BREAK.split(LINE_SEPARATOR.join(_unquoted(reply))) if part.strip()]
    for each_index, each_clause in enumerate(all_clauses):
        nearby = all_clauses[each_index + 1:each_index + 1 + MAX_REASON_SENTENCES]
        explanation = WORD_SEPARATOR.join([each_clause, *takewhile(lambda part: not (CLOSING_PHRASE.search(part) or SEPARATE_SUBJECT.search(part)), nearby)])
        if any(_warrants_review(match, each_clause, explanation, has_question) for match in CLOSING_PHRASE.finditer(each_clause)):
            return CONTINUATION_REVIEW
    return None
