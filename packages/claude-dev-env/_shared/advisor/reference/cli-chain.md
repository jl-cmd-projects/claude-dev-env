# CLI Claude-chain

Detail behind the `## CLI chain` section of [`advisor-protocol.md`](../advisor-protocol.md).
The shared runner is `python "$HOME/.claude/scripts/account_broker.py" run --product claude --report <path> -- claude <args...>`.

## Account choice

The broker applies the main account guard and chooses an eligible extra account
by remaining usage. On a usage-limit response, it tries another account. If no
account has room, it reports a reset time and exits with code 3. A non-usage
Claude failure has `JobOutcome.status == "advisor_blocked"`; the CLI exits with
code 4. The report path receives the broker's decision and attempt events.

## Tier-to-alias map

Map `selected_tier` when one exists (the warm agent already bound at or above the floor).
Map the floor tier only when the walk exhausted with `selected_tier=null`.
Resolve that tier to its CLI / Agent model alias before the first call — the CLI `--model` flag and the Agent tool `model:` field take the short aliases below.
Source of truth: `ALL_CLI_MODEL_ID_BY_TIER` and `resolve_cli_model_id(tier)` in `advisor_scripts_constants` / the `tier_model_ids.py` helper.

| Ladder tier (Title Case) | CLI / Agent `model` alias |
|---|---|
| Fable | `fable` |
| Opus | `opus` |
| Sonnet | `sonnet` |
| Haiku | `haiku` |
| ThirdParty (third-party session model field only) | `third-party` |

`resolve_cli_model_id(tier)` accepts any letter case and raises `ValueError` on a tier outside the map.

## Brief piping

Write the charter or the consult brief to a temporary file under the job's own temporary directory (or the OS temp directory when no job directory exists) and pipe it in from that file.
Drop the file once the consult completes.

## Session resume

Read the `session_id` out of the first call's JSON events or `JobOutcome.session_id`.
Pass it to `-p --resume <session_id> --output-format json` on every later consult — `-p` stays on the resume call too, since it is still a non-interactive invocation.
A session store belongs to the account that minted it. The broker keeps account affinity when that account has room. If the account reaches a usage limit, a `--resume` on another account can fail.
Treat that failure as starting over.
Resend the charter plus a compact recap of the consults since the last one, capture the new `session_id` the fresh call returns, and continue from there.
