# Astra rung

Detail behind the **Host profiles → Astra rung** section of [`advisor-protocol.md`](../advisor-protocol.md).
Open this when Opus is out of usage on a Claude or ThirdParty host and an Astra fallback bind is starting.
On a Codex host, Astra is the in-session default. See [`identity.md`](identity.md).

## Flag

`ADVISOR_ASTRA=1` (or `true` / `yes` / `on`) opens the Astra fallback after Opus is out of usage. Set the variable in the helper's process environment, or pass `--enable-astra` on the helper invocation. The CLI flag opens the rung for that run without touching the environment.
Flag off both ways: fail closed when Opus did not bind.
A Windows `setx` write only updates the persisted user environment; only a process started after that write inherits the new value, so an already-running session either sets the flag in its own invoking process environment or passes `--enable-astra`.

## Effort

`ADVISOR_EFFORT` selects Codex `model_reasoning_effort` for Astra: `low`, `medium`, `high`, `xhigh`, or `max`. The policy default is `medium`, which sends `model_reasoning_effort="medium"`. Astra Xhigh and Max requests route to Medium. Pass `--effort <level>` on the helper to set effort for that Astra run without changing the environment. An unset value uses the policy default. An unknown value blocks advisor routing.

Every fallback reply carries a `fallback_kind` field. `declined` means policy closed the rung (flag off, or the account broker named no Codex account on the `normal` tier). `broken` means the Astra path itself failed (missing executable, spawn error, timeout, malformed reply). A `broken` fallback is a defect to report.

## Preflight

Flag on: the helper asks the account broker for a Codex account first.

```
python ~/.claude/scripts/account_broker.py choose --product codex
```

**Broker path.** `codex_astra_advisor.resolve_account_broker_path` builds the broker path from the helper's own location: two directories above `_shared/advisor/scripts`, then `scripts/account_broker.py`. Installed, that is `~/.claude/scripts/account_broker.py`. Repo home: `packages/claude-dev-env/scripts/`. The accounts, their order, and sign-in steps are in [`codex-accounts.md`](../../../docs/codex-accounts.md).

The shared entry point is `~/.claude/_shared/advisor/scripts/codex_astra_advisor.py`. It runs the broker and owns Astra bind or resume parsing. Bind with `python ~/.claude/_shared/advisor/scripts/codex_astra_advisor.py --bind --enable-astra --cwd <repo-root>` and pipe the charter on stdin. Resume with `--resume <session_id>` and pipe the delta consult on stdin.

The gate passes only when the broker exits 0 and answers `decision.tier: normal` with a `decision.home` and finite session or weekly room in the matching `accounts` entry. The helper then runs Codex with `CODEX_HOME` set to `decision.home`. A `luna` or `wait` answer, including exit 3 with a wait answer, declines the preflight when Opus did not bind.

## Branches

**Preflight pass.** Bind one Codex CLI session at `gpt-6-astra` with `model_reasoning_effort` set from the policy-selected `ADVISOR_EFFORT` value, `--sandbox read-only`, and JSON output. The helper receives the standing-reviewer charter on stdin and returns only parsed ENDORSE / CORRECTION / PLAN / STOP guidance with a session ID.

**Preflight fail.** A broker failure other than exit 3 with a wait answer, timeout, malformed answer, or a `luna` or `wait` tier fails closed when Opus did not bind.

The helper owns the Astra attempt and returns an explicit fallback result. The consuming advisor path owns the Opus bind. Apply the same gate to every Astra attempt, including resume.
