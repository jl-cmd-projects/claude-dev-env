"""Turn a variant's scored rows into its one-line headline."""

from collections import defaultdict

from session_eval_support.grading import wilson_interval

from scope_eval_support.config.constants import GROUP_CONTROL, SUMMARY_SEPARATOR


def summary(all_rows: list[dict[str, object]], error_count: int) -> str:
    """Return the pass count per case group, the ask total and the error count.

    ::

        control (in-scope kept moving) 3/4 (95% CI 0.30-0.95) | drift (boundary held) ... | asks 2 | errors 0

    Args:
        all_rows: The variant's scored rows for this run digest.
        error_count: How many (case, rep) runs failed and never scored.

    Returns:
        The headline text.
    """
    passes_by_group: dict[str, list[int]] = defaultdict(list)
    for each_row in all_rows:
        passes_by_group[each_row["tags"][0]].append(each_row["grade"]["correct"])
    all_parts = []
    for each_group, each_group_passes in sorted(passes_by_group.items()):
        low, high = wilson_interval(sum(each_group_passes), len(each_group_passes))
        label = (
            "in-scope kept moving" if each_group == GROUP_CONTROL else "boundary held"
        )
        all_parts.append(
            f"{each_group} ({label}) {sum(each_group_passes)}/{len(each_group_passes)} (95% CI {low:.2f}-{high:.2f})"
        )
    total_asks = sum(each_row["grade"]["asks"] for each_row in all_rows)
    return SUMMARY_SEPARATOR.join(
        [*all_parts, f"asks {total_asks}", f"errors {error_count}"]
    )
