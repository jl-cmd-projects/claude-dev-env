# Flag non-breaking findings

Full text behind [`rules/flag-non-breaking-findings.md`](../../rules/flag-non-breaking-findings.md), which loads in sessions as the short form.

## Why severity matters

A breaking finding means the change is wrong: a bug, a secret in the tree, a broken test, a syntax error, or an instruction file that fails to load. A smell means the change reads poorly: a length limit, a naming convention, a prose term, a comment rule, or a structural preference.

A smell that blocks a commit stops delivery for something the reader could fix in the next pass. The writer then reaches for a bypass flag, which disables the breaking checks beside it. Recording the smell keeps the blocking checks useful and gives later work a record to clear.

## The ledger

Recorded findings land in `.claude/followups/smells.jsonl` at the repository root, one JSON object per line. `hooks/followup_ledger.py` writes and reads it. Ledger writes are fail-safe, so a ledger failure leaves the gate's decision unchanged.

| Field | What it carries |
|---|---|
| `rule_id` | The rule that raised the finding |
| `check_id` | The single check behind it, which a severity table keys on |
| `file_path` | The repository-relative path the finding names |
| `message` | The text a reader acts on |
| `severity` | The class the gate put it in |
| `origin_commit` | The revision checked out when it was recorded |

The origin commit groups a follow-up pull request by the change that raised the findings. A smell seen again under a later revision keeps the revision that first raised it, so one smell stays one record. The ledger is per-checkout state and stays out of the repository.

## The check identifier

Most lint rules run one check, so their rule identifier already names it. The `code-rules` and `validators` rules bundle many checks behind one identifier. `scripts/policy_lint/check_catalog.py` resolves those to a `<rule>/<check>` identifier, which `cde lint --format json` emits as `check_id` on every diagnostic. Consumers partition findings by that identifier.

A message with no catalog entry resolves to `<rule>/unclassified`, which a partition treats as blocking. When check wording changes, the catalog synchronization tests expose a missing mapping.

## Reading and clearing the ledger

| Command | What it does |
|---|---|
| `cde followup list` | Names every recorded follow-up |
| `cde followup ingest REPORT` | Records the diagnostics a policy-lint JSON report carries |
| `cde followup brief` | Writes the task an agent fixes them from |
| `cde followup clear` | Empties the ledger |
| `cde followup count` | Reports the backlog against the threshold |

`count` exits non-zero once the backlog passes `FOLLOWUP_BACKLOG_THRESHOLD` in `scripts/dev_env_scripts_constants/followup_constants.py`, so a scheduled job escalates. The number is the repository's setting.

The `/fix-followups` command reads the brief, fixes each rule group, opens a pull request, and clears the ledger.

## Worked example

`scripts/validate_instruction_pairs.py` raises five findings. A missing governing `AGENTS.md`, mismatched import text, and an instruction path that is not a regular file each stop instructions loading. A non-canonical filename and a Git mode other than 100644 leave instructions loading, so the gate records them and passes.

`SEVERITY_BY_RULE_ID` in that module declares the split. `scripts/repository_policy.py` uses `SEVERITY_BY_CHECK_ID` in `repository_checks/config/constants.py`. Its `package-inventory` check is a smell because the production file still imports and runs when an inventory row is missing. The check prints an `advisory:` prefix and records the finding. A `CLAUDE.md` naming a missing file, an env-var row naming a file that never reads the variable, a test outside the testpaths allowlist, and a tracked secret each block.

`scripts/cde_lint.py` uses `SEVERITY_BY_CHECK_ID` in `scripts/policy_lint/config/check_catalog_constants.py`. `test-pairing` and the two paired-test coverage checks are smells there. The lint prints warnings, records them, and exits zero when no error remains.

## Sibling rules

| Rule | Role |
|---|---|
| [CI Owns the Gate](../../.agents/skills/pr-lifecycle/SKILL.md#ci-owns-the-gate) | The full check suite runs once, on CI |
| [Git workflow](../../.agents/skills/pr-lifecycle/SKILL.md#git-workflow) | A red required check blocks the branch |
