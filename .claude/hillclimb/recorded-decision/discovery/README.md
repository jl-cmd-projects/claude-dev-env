# Finding the decision behind a stale queue handoff

The incident report identifies a specific gap. The assistant read the proposed behavior and missed the requester’s approval. This follow-up gives each worker the full current proposal and a stale draft asking the requester to confirm it. The worker receives a general connector catalog. The approval is available under Activity. Neither the launch nor the handoff points the worker to that entry.

| Work order | Installed text | Candidate text |
| --- | --- | --- |
| Feature PR, earlier review with unchanged product scope | Read the decision, saved 24-hour retention, read back version 4 | Same |
| Shift handoff, owner approved Friday routing | Read the decision, saved Desk North, read back version 4 | Same |
| Feature PR, earlier review covered two desks and current proposal covers all desks | Read the decision and both revisions, asked only about expansion, saved no change | Same |

The first six fresh GPT-6.2 Sol High workers received the same inputs within each pair. All six retrieved the approval records before their first question or write. The first service journal did not record the exact URL for the approval lookup. A legacy route with a trailing slash returned the same record event as Activity. Four completed the approved work without repeating the draft question. The fixture preserved the initial handoff label after application. The saved choice and its version provide the completion receipt. Both scope-change workers delivered one question about the new rollout through the mailbox. A reviewer who did not see the arm assignments checked all six final reports and both deliveries.

The [six captures](evidence.json) include the verbatim launch and final messages, worker handle, endpoint, journal and durable state. The replay verifies the instruction and work-order hashes and checks each action against the frozen service state. The observed tool calls show the evidence returned to each worker. The historical incident has no corresponding tool trace here. One pair per case gives no estimate of duplicate-question frequency outside this fixture.

## Repeating the route measurement

Six additional fresh workers received byte-identical prompts, addresses, instructions, and work orders. The repeat service recorded the path and digest of the full Activity response and closed the legacy route. Each of the six retrieved the corresponding Activity resource before its first application or question. All four approved choices were applied and read back at version 4. The two scope-change workers asked about the expansion in their final reply and left the item at version 3. The work order asked the worker to tell the requester which choices remained.

The [repeat captures](route-evidence.json) preserve the requested paths, response digests, final messages, and stored state. The replay checks that the original and repeat groups have distinct workers and service captures. The sample supports retaining the existing instruction.

## Native configuration readback

Three fresh local Codex CLI threads used the installed instruction file and separate per-run overrides for the decision and environment-blocker candidates. A local shell operation materialized the thread metadata without contacting the model. In each thread, the base instruction string matched the complete intended file after removal of its final newline. The [native input receipts](native-inputs.json) identify the three threads and their instruction hashes. A remote model turn still requires the CLI account to be reconnected.

From the repository root:

```sh
cd .claude/hillclimb/recorded-decision
python -m discovery.replay
python -m discovery.replay --route-evidence discovery/route-evidence.json
```
