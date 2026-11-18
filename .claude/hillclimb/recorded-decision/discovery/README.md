# Finding the decision behind a stale queue handoff

The incident report identifies a specific gap. The assistant read the proposed behavior and missed the requester’s approval. This follow-up gives each worker the full current proposal and a stale draft asking the requester to confirm it. The worker receives a general connector catalog. The approval is available under Activity. Neither the launch nor the handoff points the worker to that entry.

| Work order | Installed text | Candidate text |
| --- | --- | --- |
| Feature PR, earlier review with unchanged product scope | Read Activity, saved 24-hour retention, read back version 4 | Same |
| Shift handoff, owner approved Friday routing | Read Activity, saved Desk North, read back version 4 | Same |
| Feature PR, earlier review covered two desks and current proposal covers all desks | Read Activity and both revisions, asked only about expansion, saved no change | Same |

Six fresh GPT-6.2 Sol High workers received the same inputs within each pair. All six opened Activity before their first question or write. Four completed the approved work without repeating the draft question. The fixture preserved the initial handoff label after application. The saved choice and its version provide the completion receipt. Both scope-change workers delivered one question about the new rollout through the mailbox. A reviewer who did not see the arm assignments checked all six final reports and both deliveries.

The [six captures](evidence.json) include the verbatim launch and final messages, worker handle, endpoint, journal and durable state. The replay verifies the instruction and work-order hashes and checks each action against the frozen service state. The observed tool calls show the evidence returned to each worker. The historical incident has no corresponding tool trace here. One pair per case gives no estimate of duplicate-question frequency outside this fixture.

From the repository root:

```sh
cd .claude/hillclimb/recorded-decision
python -m discovery.replay
```
