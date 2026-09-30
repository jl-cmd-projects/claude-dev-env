# Cloud pstack startup verification

Status on 2026-09-30: cloud activation is blocked. Installing pstack into a
container does not establish catalog discovery, SessionStart delivery, or an
agent's early invocation. Treat those as three separate acceptance gates.

## Runtime boundary

The [OpenAI hooks reference](https://learn.chatgpt.com/docs/hooks#managed-hooks-from-requirementstoml)
excludes command handlers and hooks from local configuration and plugins under
cloud orchestration. Its managed remote MCP hook support requires an eligible
enterprise configuration and is outside this package's installer. Changing local
hook trust cannot enable the bundled shell hook on this host.

The [current cloud lifecycle](https://learn.chatgpt.com/docs/environments/cloud-environments)
distinguishes saving settings from publishing the prepared filesystem. New tasks
use published state; existing tasks retain their state. The Start skill field
contains startup instructions. Its configured value alone does not prove that a
task received it. Verify delivery in an independent task after republishing.

The [skill documentation](https://learn.chatgpt.com/docs/build-skills)
distinguishes plugin distribution in ChatGPT from standalone filesystem skills.
It also distinguishes initial skill metadata from loading the skill body. Check
the supplied catalog and every page of host discovery results before attributing
a missing entry to truncation.

## Package ownership

- `packages/claude-dev-env/bin/install-pstack-plugin.mjs` installs
  `pstack@pstack-claude` from `michael-denyer/pstack-claude` through each CLI.
  A successful CLI exit reports installation for that CLI home.
- `packages/claude-dev-env/bin/codex-skill-load-block.mjs` writes a load
  instruction into the selected `CODEX_HOME/AGENTS.md`. Delivery depends on the
  host loading that instruction file.
- The upstream pstack plugin owns `.codex-plugin/plugin.json`, its `skills/`
  directory, and `hooks/codex-hooks.json`. Version 0.9.53 registers SessionStart
  for `startup|resume|clear|compact`, running `session-start.sh codex`. That script
  emits `session-start-context.md` unless the model sheet disables the hook.
- The cloud plugin catalog is a separate host-managed input. This repository
  cannot add entries to that catalog by writing into a CLI plugin cache.

Preserve the running host's `CODEX_HOME`, credentials, custom configuration, and
hook trust. Keep persistent package assets separate from the runtime home.
Keep environment publication and admin-managed hook changes under
their existing approval process.

## Fresh-task fixture

Run these as separate cloud tasks with no inherited task history. Record the
repository commit, published environment revision, plugin version, task URL, and
exact prompt before starting. The parent retains the transcript. Do not paste
this entire guide into the automatic-start task.

### Task A: explicit availability probe

Use this prompt verbatim:

```text
Before any manual file read, report whether your supplied skill catalog includes
pstack:poteto-mode or an equivalent poteto-mode entry, and whether initial startup
context instructed you to invoke it. Quote its catalog name and locator if present.
If available, invoke that catalog skill now. Record the invocation call and its
result. If absent, report that and list host skill discovery results, following
all pagination. Do not substitute a guessed package locator, filesystem read,
wrapper, or nested CLI session. This prompt explicitly requests invocation, so
success here proves availability only, not automatic startup.
```

### Task B: automatic-start probe

Use this prompt verbatim:

```text
Investigate why the installer can report pstack installed while a newly launched
agent cannot discover its workflow. Inspect the installer and propose the smallest
supported correction. Do not edit files or change settings. At the end, report
which startup instructions and skill metadata you received before reading files,
and list your first three assistant action rounds with their tool calls.
```

For this fixture, an action round is one assistant response ending in a tool call
or final answer; calls batched in one response belong to one round. Preserve the
host's own turn identifiers alongside this count. The reviewer checks the first
three rounds in the transcript, including successful skill-load results. A claim
in the final answer without the matching tool result is insufficient.

## Acceptance ledger

Record each gate as pass, fail, or unverified, with transcript locations:

| Gate | Required evidence |
| --- | --- |
| Catalog | Initial supplied metadata or host skill discovery exposes poteto-mode and its load succeeds |
| SessionStart | Host lifecycle evidence identifies SessionStart and the delivered instruction to invoke poteto-mode |
| Early invocation | Task B loads the catalog skill in rounds 1-3 and follows its instructions |

An AGENTS instruction or a Start skill receipt has its own provenance. It does
not establish that SessionStart ran. An explicit Task A invocation cannot pass
Task B. A later filesystem read cannot change the pre-read catalog observation.
Existing `tests/fresh-session` harness checks and nested CLI sessions cover their
own transports; they do not replace this cloud transcript.

If a gate fails, retain the failure and its owner. Missing cloud skill metadata
requires a cloud plugin publication/discovery investigation. Missing Start skill
delivery requires an environment lifecycle investigation. Unsupported plugin
SessionStart requires a platform capability decision. Do not advertise a local
installer change as resolving these host-owned failures.

Resume acceptance after the parent publishes an eligible configuration and runs
both tasks. If the SessionStart requirement remains mandatory on a host without
support, report the platform block and request a supported host or platform change.
