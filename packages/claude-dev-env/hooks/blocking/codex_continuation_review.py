"""Check visible closing prose for a reason to revisit the user's assignment once."""

from final_reply_gate import prose_paragraphs
from hooks_constants.codex_continuation_constants import (
    ADDITIONAL_REQUEST,
    APPROVAL_SUBJECT,
    CANCELLED_REQUEST,
    CLAUSE_BREAK,
    CLOSING_PHRASE,
    CONTINUATION_REVIEW,
    MAX_REASON_SENTENCES,
    NEGATED_STATUS,
    ONLY_STATUS_REQUEST,
    PROTECTED_DECISION,
    QUOTED_EXAMPLE,
    REGISTERED_WAKE,
    RESOLVED_STATUS,
    STANDALONE_STOP,
    WAIT_SUBJECT,
)


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
    request = " ".join(QUOTED_EXAMPLE.sub(" ", part) for part in prose_paragraphs(user_request)).strip()
    if STANDALONE_STOP.fullmatch(request) or ONLY_STATUS_REQUEST.fullmatch(request):
        return None
    if CANCELLED_REQUEST.search(request) and not ADDITIONAL_REQUEST.search(request):
        return None
    prose = "\n".join(" ".join(QUOTED_EXAMPLE.sub(" ", part).split()) for part in prose_paragraphs(reply))
    all_clauses = [clause.strip() for clause in CLAUSE_BREAK.split(prose) if clause.strip()]
    for each_index, each_clause in enumerate(all_clauses):
        for each_match in CLOSING_PHRASE.finditer(each_clause):
            if NEGATED_STATUS.search(each_clause[:each_match.start()]) or RESOLVED_STATUS.search(each_clause[each_match.end():]):
                continue
            context = [each_clause]
            for next_clause in all_clauses[each_index + 1:each_index + 1 + MAX_REASON_SENTENCES]:
                if CLOSING_PHRASE.search(next_clause):
                    break
                context.append(next_clause)
            explanation = " ".join(context)
            if APPROVAL_SUBJECT.search(each_clause) and (has_question or PROTECTED_DECISION.search(explanation)):
                continue
            if any(wait.start() <= each_match.start() and wait.end() >= each_match.end() for wait in WAIT_SUBJECT.finditer(each_clause)) and (REGISTERED_WAKE.search(explanation) or PROTECTED_DECISION.search(explanation)):
                continue
            return CONTINUATION_REVIEW
    return None
