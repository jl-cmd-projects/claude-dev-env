# Oversee delegated work

Every agent that spawns a subagent, thread, or session owns that work until it reaches the user.
Agents make mistakes. A fresh `verifier` agent, separate from the worker, catches them before they reach the user.
The `spawn_oversight_hook` adds this duty to the first spawn of each agent in the tree, and again after a compaction.

- Run each piece through the verified-work flow in `~/.claude/docs/rule-guides/verified-work.md`: research, verify, plan, verify, implement, verify.
- Brief each worker with the user's own words, the standards that apply, and the acceptance check.
- Brief each verifier with the issue, the sources, the old state, and the new state. Leave the worker's conclusion out.
- While a worker runs, read its progress. Wake a quiet agent with one concrete next step.
- A fix passes only when its verifier reproduced the issue on the old state and confirmed it gone on the new state.
- Send a FAIL back to the worker with the verifier's evidence, and give the next attempt a new verifier.
- Tag each piece in-scope or new scope. Ask the user once before building new scope, and keep in-scope work moving.
- Keep each brief, prompt, and context file you hand an agent a short map: when to use it, the steps, and pointers to reference files it opens on demand.
- Report as done only what a verifier passed, and name the verdict and its evidence. Report the rest as waiting on verification.

When the user asks for silence, such as "silent unless something merges or you are blocked", the coordinator sets each watcher to emit only the events the user named. It briefs each delegate to send one final report and to start no watch loop that ends its turn. Every other event starts a turn the user did not ask to see, and `hooks/session/background_silence_prompt.py` tells that turn to end with no text.
