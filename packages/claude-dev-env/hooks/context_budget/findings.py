"""Compare a context file with its kind limits and its over-budget entry.

::

    unlisted file   lines > limit                         -> file finding
                    unpointed section > detail limit      -> section finding
    listed file     lines null, lines > limit             -> file finding
                    lines N, lines > limit and lines > N  -> grown finding
                    section heading not recorded          -> section finding
    CI ratchet      changed file below its record N       -> record the new count, or null
                    changed file lost a recorded section  -> drop it from the entry
                    changed file within budget            -> remove the entry
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable

from context_budget.model import (
    BaselineEntry,
    BudgetFinding,
    BudgetPolicy,
    FileMeasure,
    SectionScan,
)
from context_budget.sections import baseline_entry_for, measure_file
from hooks_constants.context_budget_constants import (
    FILE_FINDING_TEMPLATE,
    FILE_SCOPE,
    GROWN_FINDING_TEMPLATE,
    GROWN_PAST_PRIOR_TEMPLATE,
    KEBAB_SEPARATOR,
    LINES_KEY,
    NON_KEBAB_CHARACTER_PATTERN,
    RATCHET_LOWER_TEMPLATE,
    RATCHET_REMOVE_TEMPLATE,
    SECTION_FINDING_TEMPLATE,
    SECTIONS_KEY,
)


def _kebab(heading: str) -> str:
    return NON_KEBAB_CHARACTER_PATTERN.sub(KEBAB_SEPARATOR, heading.lower()).strip(KEBAB_SEPARATOR)


def _section_finding(relative_path: str, scan: SectionScan, limit: int) -> BudgetFinding:
    return BudgetFinding(
        relative_path,
        scan.heading,
        SECTION_FINDING_TEMPLATE.format(
            path=relative_path,
            heading=scan.heading,
            count=scan.detail_line_count,
            limit=limit,
            kebab=_kebab(scan.heading),
        ),
    )


def _unrecorded_sections(
    all_sections: Iterable[SectionScan], all_recorded_headings: Iterable[str]
) -> list[SectionScan]:
    remaining_count_by_heading = Counter(all_recorded_headings)
    all_unrecorded: list[SectionScan] = []
    for each_scan in all_sections:
        if remaining_count_by_heading[each_scan.heading] > 0:
            remaining_count_by_heading[each_scan.heading] -= 1
        else:
            all_unrecorded.append(each_scan)
    return all_unrecorded


def _entry_json(entry: BaselineEntry) -> str:
    return json.dumps({LINES_KEY: entry.lines, SECTIONS_KEY: list(entry.all_section_headings)})


def _ratchet_message(
    relative_path: str, measure: FileMeasure, current: BaselineEntry, recorded: BaselineEntry
) -> str:
    return RATCHET_LOWER_TEMPLATE.format(
        path=relative_path,
        recorded_entry_json=_entry_json(recorded),
        count=measure.line_count,
        sections=json.dumps(list(current.all_section_headings)),
        entry_json=_entry_json(current),
    )


def _ratchet_findings(
    relative_path: str, measure: FileMeasure, recorded: BaselineEntry
) -> list[BudgetFinding]:
    current = baseline_entry_for(measure)
    if current is None:
        message = RATCHET_REMOVE_TEMPLATE.format(path=relative_path, count=measure.line_count)
        return [BudgetFinding(relative_path, FILE_SCOPE, message)]
    has_lost_section = bool(
        Counter(recorded.all_section_headings) - Counter(current.all_section_headings)
    )
    has_dropped_lines = recorded.lines is not None and (
        current.lines is None or current.lines < recorded.lines
    )
    if not has_dropped_lines and not has_lost_section:
        return []
    message = _ratchet_message(relative_path, measure, current, recorded)
    return [BudgetFinding(relative_path, FILE_SCOPE, message)]


def _line_limit_findings(relative_path: str, measure: FileMeasure) -> list[BudgetFinding]:
    limit = measure.kind.line_limit or 0
    if measure.line_count <= limit:
        return []
    message = FILE_FINDING_TEMPLATE.format(
        path=relative_path, count=measure.line_count, kind=measure.kind.name, limit=limit
    )
    return [BudgetFinding(relative_path, FILE_SCOPE, message)]


def _grown_findings(
    relative_path: str, measure: FileMeasure, recorded: BaselineEntry, grown_template: str
) -> list[BudgetFinding]:
    if recorded.lines is None:
        return _line_limit_findings(relative_path, measure)
    limit = measure.kind.line_limit or 0
    if measure.line_count <= max(recorded.lines, limit):
        return []
    message = grown_template.format(
        path=relative_path,
        recorded=recorded.lines,
        count=measure.line_count,
        kind=measure.kind.name,
        limit=limit,
    )
    return [BudgetFinding(relative_path, FILE_SCOPE, message)]


def _file_scope_findings(
    relative_path: str,
    measure: FileMeasure,
    recorded: BaselineEntry | None,
    is_ratchet_due: bool,
    grown_template: str,
) -> tuple[list[BudgetFinding], list[SectionScan]]:
    if recorded is None:
        return _line_limit_findings(relative_path, measure), list(measure.all_over_limit_sections)
    all_findings = _grown_findings(relative_path, measure, recorded, grown_template)
    if is_ratchet_due:
        all_findings.extend(_ratchet_findings(relative_path, measure, recorded))
    all_new_sections = _unrecorded_sections(
        measure.all_over_limit_sections, recorded.all_section_headings
    )
    return all_findings, all_new_sections


def file_findings(
    policy: BudgetPolicy, relative_path: str, text: str, ratchet_prior_text: str | None
) -> tuple[BudgetFinding, ...]:
    """Check one file against its kind and the over-budget list.

    Args:
        policy: Budget policy.
        relative_path: Repository-relative POSIX path.
        text: Current file text.
        ratchet_prior_text: Prior text when the CI ratchet applies, else None.

    Returns:
        Findings in file-then-section order.
    """
    measure = measure_file(policy, relative_path, text)
    if measure is None:
        return ()
    recorded = policy.baseline_entry_by_path.get(relative_path)
    is_ratchet_due = ratchet_prior_text is not None and ratchet_prior_text != text
    grown_template = (
        GROWN_PAST_PRIOR_TEMPLATE if policy.is_baseline_the_prior_text else GROWN_FINDING_TEMPLATE
    )
    all_findings, all_new_sections = _file_scope_findings(
        relative_path, measure, recorded, is_ratchet_due, grown_template
    )
    return (
        *all_findings,
        *(_section_finding(relative_path, each, policy.section_detail_line_limit)
          for each in all_new_sections),
    )


def _with_prior_as_baseline(
    policy: BudgetPolicy, relative_path: str, prior_text: str
) -> BudgetPolicy:
    prior_measure = measure_file(policy, relative_path, prior_text)
    prior_entry = None if prior_measure is None else baseline_entry_for(prior_measure)
    if prior_entry is None:
        return policy
    return BudgetPolicy(
        policy.section_detail_line_limit,
        policy.all_kinds,
        policy.all_hooks,
        {**policy.baseline_entry_by_path, relative_path: prior_entry},
        policy.baseline_characters_by_hook_name,
        is_baseline_the_prior_text=True,
    )


def _introduced(
    all_post_findings: Iterable[BudgetFinding],
    all_prior_findings: Iterable[BudgetFinding],
    has_grown: bool,
) -> tuple[BudgetFinding, ...]:
    remaining_count_by_scope = Counter(each.scope for each in all_prior_findings)
    all_introduced: list[BudgetFinding] = []
    for each_finding in all_post_findings:
        if each_finding.scope == FILE_SCOPE:
            is_new = has_grown
        else:
            is_new = remaining_count_by_scope[each_finding.scope] <= 0
            remaining_count_by_scope[each_finding.scope] -= 1
        if is_new:
            all_introduced.append(each_finding)
    return tuple(all_introduced)


def edit_findings(
    policy: BudgetPolicy,
    relative_path: str,
    prior_text: str | None,
    post_text: str,
    is_prior_the_baseline: bool,
) -> tuple[BudgetFinding, ...]:
    """Return the findings an edit adds; a file finding needs added lines.

    Args:
        policy: Budget policy.
        relative_path: Repository-relative POSIX path.
        prior_text: On-disk text before the edit, or None for a new file.
        post_text: Text the edit leaves.
        is_prior_the_baseline: Whether the prior text is the baseline entry.

    Returns:
        Findings present after the edit and absent before it.
    """
    if prior_text is None:
        return file_findings(policy, relative_path, post_text, None)
    effective_policy = policy
    if is_prior_the_baseline:
        effective_policy = _with_prior_as_baseline(policy, relative_path, prior_text)
    return _introduced(
        file_findings(effective_policy, relative_path, post_text, None),
        file_findings(effective_policy, relative_path, prior_text, None),
        len(post_text.splitlines()) > len(prior_text.splitlines()),
    )
