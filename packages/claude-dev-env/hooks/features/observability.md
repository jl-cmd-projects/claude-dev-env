# Observability

This family records instruction loads and file edits for later checks.

## Checks

- `observability/instructions_loaded_logger.py` writes selected instruction-load fields to a JSONL log.
- `observability/session_file_edit_tracker.py` records edited file paths in a per-session tracker for the stage gate.

## When it fires

- `observability/instructions_loaded_logger.py` runs on `InstructionsLoaded`, matcher `session_start|nested_traversal|path_glob_match|include|compact`, timeout `10` seconds in `hooks.json`.
- `observability/session_file_edit_tracker.py` runs on `PostToolUse`, matcher `Write|Edit|MultiEdit|apply_patch`, timeout `30` seconds in `hooks.json`.

## Proving it

Preconditions:

- Run each command from the repository root with Python and pytest available. The tests redirect log and tracker paths to disposable directories.

- **Instruction log.** Input is an `InstructionsLoaded` payload with a file path and load reason. Run `python -m pytest packages/claude-dev-env/hooks/observability/test_instructions_loaded_logger.py -q`. The adjacent test observes one JSONL record with the selected fields.
- **Edit tracker.** Input is a Write payload with a file path and session ID. Run `python -m pytest packages/claude-dev-env/hooks/observability/test_session_file_edit_tracker.py -q`. The adjacent test observes the resolved path in that session's tracker.

## Gotchas

- The instruction logger keeps only selected payload fields. It exits zero if logging fails.
- The edit tracker never blocks a tool call. Its per-session file is read later by the stage gate.
- The investigation reset applies to delegation tools. Its companion investigation gate lives outside this Claude hook registration map.
