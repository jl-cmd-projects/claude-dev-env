# Batch JSON spec

Shape:

```json
{
  "role": "bugteam",
  "should_ping": false,
  "workers": [
    {
      "role_name": "investigate-hooks",
      "prompt_parts": [
        "/abs/path/to/readonly-brief.md",
        "/abs/path/to/task-body.md",
        "/abs/path/to/report-contract.md"
      ],
      "cwd": "/abs/path/to/worktree",
      "tool_profile": "readonly",
      "timeout_seconds": 600,
      "is_repo_only": true,
      "agent_name": "poteto-agent"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `role` | Preflight role configuration to check (default `bugteam`) |
| `should_ping` | When true, preflight runs the opt-in live ping |
| `workers` | Non-empty list of worker objects |
| `role_name` | Label on the summary report for this worker |
| `prompt_parts` | Ordered absolute paths to part files |
| `cwd` | Working directory for that worker |
| `tool_profile` | `readonly` or `build` |
| `timeout_seconds` | Per-worker timeout (default 600, ceiling 5400). A spec asking for more is refused |
| `is_repo_only` | Readonly only: when true, also pass `--disable-web-search` |
| `agent_name` | Use `poteto-agent`; prompts carry the worker role. |

Workers run with no turn cap. The timeout is the only bound on a worker's
length, and a worker that hits it is killed with its whole process tree and
reported as `timeout`.

A worker entry accepts these fields and no others. Any other key fails the
load with an error naming the stray key and listing the accepted set, so a
misspelled field fails at startup.

Put the spec file under the run state directory (or any path you pass to
`--spec`).
