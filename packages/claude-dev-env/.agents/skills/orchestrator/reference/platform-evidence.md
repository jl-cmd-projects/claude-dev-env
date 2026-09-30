# Coordinator evidence and runtime boundaries

Use this reference when adapting the role to Claude Projects or another runtime.
Product facts below were checked on September 30, 2026.

## Official product evidence

Anthropic's [Projects redesign announcement](https://claude.com/blog/projects-redesigned), dated September 17, 2026,
describes a coordinator that routes work to threads, reviews results, and tracks progress.
It describes shared memory and a library of supplied files and produced artifacts.
Each cloud thread has its own context, branch, and repository copy.

The current [Claude Code Projects documentation](https://code.claude.com/docs/en/claude-projects)
documents the coordinator, persistent threads, indexed project memory, PR watchers, and project routines.
It documents a single-user beta and a local-thread path through Remote Control.
Local threads receive project instructions but do not load project memory files into context.
The instructions limit is 16,000 characters. That limit does not describe total project-memory storage.
The September launch post predates the documented local-thread path.

These product mechanisms do not become ordinary-session tools when this skill loads.
The run registry, task authority, and evidence files provide this skill's recovery contract.
Verify which tool capabilities the current executor exposes before selecting an implementation.

## Coordinator reports

The September 30, 2026 coordinator account reports observations from two project workspaces.
The second coordinator reviewed and corrected the first account.
Both report per-turn reminders. One reports a Stop hook firing; the other did not observe that firing.
The account's private helper interfaces, event payloads, memory limits, and access boundaries remain reported evidence.
They are not universal platform guarantees or authorization to install their suggested mechanisms.

The skill adopts message sorting, brief source wording, one writer per file, claim verification, and bounded parent context.
It keeps stable preferences, changing task state, and historical snapshots in separate roles.
Timing rules, model choices, memory writes, and external actions follow the current user's and runtime's instructions.
The private source stays outside the public skill package.

## Runtime mechanisms

| Mechanism | Supported scope |
|---|---|
| [Claude Code hooks](https://code.claude.com/docs/en/hooks) | Documented lifecycle events such as SessionStart, PreCompact, and SubagentStop. Configuration and loading need separate verification. |
| [Claude Code subagents](https://code.claude.com/docs/en/sub-agents) | Bounded worker contexts. Supply the facts and owned paths needed for the task. |
| [Agent Teams](https://code.claude.com/docs/en/agent-teams) | A separate experimental facility with resume limitations. Reconcile worker liveness after recovery. |
| [Routines](https://code.claude.com/docs/en/routines) | Scheduled or event-triggered work with its own execution and authorization boundaries. |
| [Remote Control](https://code.claude.com/docs/en/remote-control) | A local executor with local availability and permissions. |

A PreCompact snapshot helps with a known compaction. Save state as work changes to cover abrupt context loss.
Report a hook as active only after observing its installed configuration and supported invocation.
Keep a missing hook or event-delivery capability visible without claiming that the skill enables it.
