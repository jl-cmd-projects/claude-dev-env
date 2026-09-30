---
name: e-code-review
description: >-
  Code review at one of five effort levels that match the built-in
  /code-review recipes step for step: low, medium, high, xhigh, max.
  Triggers: /e-code-review with an optional level and an optional --fix.
---

# e-code-review

**Pick a level, load its file, run it.** Each file has the same steps, angles, caps, and fields as the built-in `/code-review` recipe for that level. Only the wording differs, where this repo's prose rules require it.

| Level | File | Shape |
|---|---|---|
| `low` | [reference/low.md](reference/low.md) | 1 diff pass, no verify, at most 4 findings |
| `medium` | [reference/medium.md](reference/medium.md) | 1 careful diff pass, at most 15 findings |
| `high` | [reference/high.md](reference/high.md) | 8 inline angles, dedup with no verify, at most 10 findings |
| `xhigh` | [reference/xhigh.md](reference/xhigh.md) | 10 inline angles, dedup, gap sweep, at most 15 findings |
| `max` | [reference/max.md](reference/max.md) | 10 subagent angles, 1-vote verify, gap sweep, at most 15 findings |

## Level

With no level, or an unknown one, run `high`.

## Target

A PR number, branch name, or file path after the level is the review target. With no target, the review reads the current diff.

## Report

Each level file reports through the ReportFindings tool. When the host has no ReportFindings tool, print the findings in its place, most severe first, one per line as `file:line — summary`. `--fix` reports its outcomes the same way, with the outcome at the end of each line.

## --fix

`--fix` works with every level. It lives in one file, [reference/fix.md](reference/fix.md). No level file carries its own fix steps.

## The process

### Native GitHub evidence pilot

Keep one coordinator responsible for native review requests. Record the request comment and full candidate head. Read raw GitHub review records to retain commit_id; normalized connector output can omit it. Completed reviews can contain findings. The quota_notice_ids field records historical usage-limit comments. Driver replies and resolved threads provide no clean completion proof.

Inspect a candidate from the shared source checkout:

```powershell
python packages/claude-dev-env/scripts/codex_review_observer.py <owner/repository> <pull-request> <full-head>
python -m pytest packages/claude-dev-env/scripts/tests/test_codex_review_observer.py packages/claude-dev-env/scripts/tests/test_codex_review_guidance.py -q --override-ini="addopts=" -p no:cacheprovider
```

The current observer holds admission for every supported diagnostic. Require captured successful native completion with full-head and attempt coverage before adding a clean verdict. After a repair push, review the new head and preserve all existing checks. Keep current repository contracts authoritative over copied hosted policy.

1. Read the level and the optional `--fix` flag. Load the level file.
2. Run it end to end, ending in its ReportFindings call.
3. With `--fix`, load `reference/fix.md` and run it on those findings.
