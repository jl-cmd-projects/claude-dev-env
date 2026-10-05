# Oversee delegated work

Every agent that spawns a subagent, thread, or session owns that work until it reaches the user.
Agents make mistakes. The spawner is a fresh second set of eyes that catches and corrects them before they reach the user.
The `spawn_oversight_hook` adds this duty to every spawn, at every level of the tree.

- Brief each agent with the user's own words, the standards that apply, and the acceptance check.
- While it runs, read its progress. Wake a quiet agent with one concrete next step.
- Before its output reaches the user, check it against the user's words and standards yourself.
- Send the agent a correction when it misses, and check the corrected output the same way.
- Give each piece of a multi-piece task its own reviewer or helper.
- Show the user you are involved: say what you checked and what you corrected.
