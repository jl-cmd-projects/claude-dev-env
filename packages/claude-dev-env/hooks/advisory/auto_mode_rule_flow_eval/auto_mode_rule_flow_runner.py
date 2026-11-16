#!/usr/bin/env python3
"""Run the auto mode rule flow cases against a refusal hook and a Stop gate.

Each case is a list of events played in order in a fresh scratch home::

    {"refusal": {...}, "name": "a"}   -> PermissionDenied payload to the refusal hook
    {"transcript": "ask", ...}         -> answered AskUserQuestion records appended
    {"stop": {...}}                    -> Stop payload to the Stop gate

A refusal event that adds one ledger file binds that file to its ``name``.
Expectations read only hook output (stdout JSON and exit code) and the
``answer`` field of the ledger files, so a case never depends on the ledger's
id rule. A ledger file is any JSON object with an ``answer`` key under
``<config>/state/auto-mode-refusals/<session_id>/``.

A case passes when every expectation holds, fails when one does not, and is an
error when a hook is missing, times out, exits with an unexpected code, or
prints output that is not a JSON object. ``HOME`` and ``CLAUDE_CONFIG_DIR``
always point into the scratch folder. Of the calling shell's variables, only
``PATH``, ``LANG``, ``SYSTEMROOT``, ``TEMP`` and ``TMP`` reach a hook.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_hooks_root_directory = str(Path(__file__).resolve().parent.parent.parent)
if _hooks_root_directory not in sys.path:
    sys.path.insert(0, _hooks_root_directory)

from hooks_constants.auto_mode_rule_flow_runner_constants import (
    ALL_BASE_ENVIRONMENT_VARIABLE_NAMES,
    ALLOW_STUB_FILE_NAME,
    ALL_CASE_KINDS,
    ALL_LEDGER_RELATIVE_PARTS,
    ALL_QUESTION_OPTIONS,
    ALL_REFUSAL_EXPECT_KEYS,
    ALL_STOP_EXIT_CODES,
    ALL_STOP_EXPECT_KEYS,
    ANSWER_FIELD,
    ANSWER_PAIR_SEPARATOR,
    ANSWERED_RESULT_TEMPLATE,
    ASK_TOOL_NAME,
    ASK_TRANSCRIPT_KIND,
    BASH_RESULT_TEXT,
    BASH_TOOL_NAME,
    BASH_TRANSCRIPT_KIND,
    BLOCK_DECISION,
    CALIBRATED_LINE,
    CALIBRATION_PROBLEM_TEMPLATE,
    CARD_RESULT_TEXT,
    CARD_TRANSCRIPT_KIND,
    CASE_FILE_NAME,
    CONFIG_DIRECTORY_NAME,
    CONFIG_DIRECTORY_VARIABLE,
    DEFAULT_QUESTION_HEADER,
    DEFAULT_REFUSAL_HOOK_RELATIVE_PATH,
    DEFAULT_STOP_HOOK_RELATIVE_PATH,
    ERROR_RULE_LINE,
    ERROR_VERDICT,
    ERRORS_KEY,
    ERRORED_RESULT_CONTENT,
    ERRORED_TOOL_USE_RESULT,
    FAIL_VERDICT,
    FLOW_MISSING_FILE,
    FLOW_OFF,
    FLOW_ON,
    HOLD_EXIT_CODE,
    HOLD_STUB_FILE_NAME,
    HOME_VARIABLE,
    HOOK_TIMEOUT_SECONDS,
    LEDGER_PLACEHOLDER_PATTERN,
    MAIN_SESSION_ID,
    MISSING_PLAYBOOK_RELATIVE_PATH,
    NO_BYTECODE_VALUE,
    NO_BYTECODE_VARIABLE,
    PASS_VERDICT,
    PERMISSION_DENIED_EVENT_NAME,
    PERMISSION_MODE,
    PLAYBOOK_PLACEHOLDER,
    PLAYBOOK_RELATIVE_PATH,
    PLAYBOOK_TEXT,
    PLAYBOOK_VARIABLE,
    PROBLEM_LINE_INDENT,
    REFUSAL_EVENT_KEY,
    GIT_FILE_TEMPLATE,
    RULE_REPOSITORY_NAME,
    RULE_TOOL_RELATIVE_PATH,
    RULE_TOOL_TEXT,
    RULE_WORKTREE_NAME,
    SCRATCH_GIT_NAME,
    SCRATCH_HEAD_TEXT,
    SCRATCH_PLACEHOLDER,
    WORKTREE_COMMON_DIRECTORY_TEXT,
    WORKTREE_BACK_POINTER_NAME,
    WORKTREE_GIT_RELATIVE_PATH,
    SHOULD_ACT_PASSED_KEY,
    SHOULD_ACT_KIND,
    SHOULD_STAY_QUIET_KIND,
    SHOULD_STAY_QUIET_PASSED_KEY,
    STOP_EVENT_KEY,
    STOP_EVENT_NAME,
    SUMMARY_LINE_TEMPLATE,
    TIMED_OUT_EXIT_CODE,
    TIMED_OUT_STDOUT,
    TIMESTAMP_FORMAT,
    TRANSCRIPT_EVENT_KEY,
    TRANSCRIPT_FILE_NAME,
    UNBOUND_LEDGER_TEMPLATE,
)
from hooks_constants.windows_filesystem import force_rmtree

JsonObject = dict[str, object]


class CaseFileInvalid(ValueError):
    """The case file holds a case the runner cannot read."""


@dataclass(frozen=True)
class HookRun:
    """One hook invocation.

    Attributes:
        exit_code: The process exit code, or None when the hook file is missing.
        stdout: The text the hook printed on stdout.
    """

    exit_code: int | None
    stdout: str


@dataclass(frozen=True)
class CaseOutcome:
    """The graded result of one case.

    Attributes:
        case_id: The case id, such as ``R1``.
        kind: ``should act`` or ``should stay quiet``.
        verdict: ``pass``, ``fail`` or ``error``.
        all_problems: One line per expectation that did not hold or hook that broke.
    """

    case_id: str
    kind: str
    verdict: str
    all_problems: tuple[str, ...]


@dataclass
class _Scratch:
    root: Path
    refusal_hook: Path
    stop_hook: Path
    all_today_outputs: dict[str, str]
    ledger_path_by_name: dict[str, Path] = field(default_factory=dict)
    all_errors: list[str] = field(default_factory=list)
    all_failures: list[str] = field(default_factory=list)
    tool_use_counter: int = 0

    @property
    def config_directory(self) -> Path:
        return self.root / CONFIG_DIRECTORY_NAME

    @property
    def transcript_path(self) -> Path:
        return self.root / TRANSCRIPT_FILE_NAME

    @property
    def playbook_path(self) -> Path:
        return self.root / PLAYBOOK_RELATIVE_PATH


def ledger_directory_for(config_directory: Path, session_id: str) -> Path:
    """Return the folder that holds one session's ledger files.

    Args:
        config_directory: The scratch ``CLAUDE_CONFIG_DIR``.
        session_id: The session the refusals belong to.

    Returns:
        ``<config>/state/auto-mode-refusals/<session_id>``.
    """
    return config_directory.joinpath(*ALL_LEDGER_RELATIVE_PARTS, session_id)


def read_ledger_answers(config_directory: Path, session_id: str) -> dict[Path, object]:
    """Return each ledger file of a session mapped to its ``answer`` field.

    ::

        a.json {"answer": null, ...}      -> {a.json: None}
        q.json {"question": "...", ...}   -> skipped, it has no answer key

    Args:
        config_directory: The scratch ``CLAUDE_CONFIG_DIR``.
        session_id: The session whose folder is read.

    Returns:
        The answer of every JSON object in the folder that has an ``answer`` key.
    """
    ledger_directory = ledger_directory_for(config_directory, session_id)
    answer_by_path: dict[Path, object] = {}
    if not ledger_directory.is_dir():
        return answer_by_path
    for each_path in sorted(ledger_directory.glob("*.json")):
        try:
            parsed_file = json.loads(each_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(parsed_file, dict) and ANSWER_FIELD in parsed_file:
            answer_by_path[each_path] = parsed_file[ANSWER_FIELD]
    return answer_by_path


def _substituted(template: object, scratch: _Scratch) -> object:
    if isinstance(template, str):
        replaced_text = template.replace(PLAYBOOK_PLACEHOLDER, str(scratch.playbook_path))
        replaced_text = replaced_text.replace(SCRATCH_PLACEHOLDER, str(scratch.root))
        return re.sub(
            LEDGER_PLACEHOLDER_PATTERN,
            lambda each_match: _ledger_text_for(each_match.group("name"), scratch),
            replaced_text,
        )
    if isinstance(template, list):
        return [_substituted(each_entry, scratch) for each_entry in template]
    if isinstance(template, dict):
        return {
            each_key: _substituted(each_entry, scratch) for each_key, each_entry in template.items()
        }
    return template


def _ledger_text_for(name: str, scratch: _Scratch) -> str:
    bound_path = scratch.ledger_path_by_name.get(name)
    return str(bound_path) if bound_path else UNBOUND_LEDGER_TEMPLATE.format(name=name)


def _hook_environment(event: JsonObject, scratch: _Scratch) -> dict[str, str]:
    all_variables = {
        each_name: os.environ[each_name]
        for each_name in ALL_BASE_ENVIRONMENT_VARIABLE_NAMES
        if each_name in os.environ
    }
    all_variables[HOME_VARIABLE] = str(scratch.root)
    all_variables[CONFIG_DIRECTORY_VARIABLE] = str(scratch.config_directory)
    all_variables[NO_BYTECODE_VARIABLE] = NO_BYTECODE_VALUE
    flow_setting = event.get("flow", FLOW_ON)
    playbook_path_by_flow = {
        FLOW_ON: scratch.playbook_path,
        FLOW_MISSING_FILE: scratch.root / MISSING_PLAYBOOK_RELATIVE_PATH,
    }
    if flow_setting in playbook_path_by_flow:
        all_variables[PLAYBOOK_VARIABLE] = str(playbook_path_by_flow[flow_setting])
    elif flow_setting != FLOW_OFF:
        raise CaseFileInvalid(f"unknown flow setting {flow_setting!r}")
    all_extra_variables = _substituted(event.get("env", {}), scratch)
    if isinstance(all_extra_variables, dict):
        all_variables.update(
            {str(each_name): str(each_text) for each_name, each_text in all_extra_variables.items()}
        )
    return all_variables


def _run_hook(
    hook_path: Path, payload: JsonObject, all_variables: dict[str, str], scratch: _Scratch
) -> HookRun:
    if not hook_path.is_file():
        return HookRun(exit_code=None, stdout="")
    try:
        completed = subprocess.run(
            [sys.executable, str(hook_path)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=all_variables,
            cwd=str(scratch.root),
            timeout=HOOK_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return HookRun(exit_code=TIMED_OUT_EXIT_CODE, stdout=TIMED_OUT_STDOUT)
    return HookRun(exit_code=completed.returncode, stdout=completed.stdout)


def _parsed_stdout(hook_run: HookRun) -> JsonObject | None:
    if not hook_run.stdout.strip():
        return {}
    try:
        parsed_stdout = json.loads(hook_run.stdout)
    except ValueError:
        return None
    return parsed_stdout if isinstance(parsed_stdout, dict) else None


def _check_ledger(expect: JsonObject, session_id: str, label: str, scratch: _Scratch) -> None:
    answer_by_path = read_ledger_answers(scratch.config_directory, session_id)
    if "entry_count" in expect and len(answer_by_path) != expect["entry_count"]:
        scratch.all_failures.append(
            f"{label}: expected {expect['entry_count']} ledger entries, found {len(answer_by_path)}"
        )
    all_expected_answers = expect.get("answers", {})
    if not isinstance(all_expected_answers, dict):
        raise CaseFileInvalid(f"{label}: answers must be an object")
    for each_name, each_expected_answer in all_expected_answers.items():
        bound_path = scratch.ledger_path_by_name.get(each_name)
        if bound_path is None or bound_path not in answer_by_path:
            scratch.all_failures.append(f"{label}: no ledger entry for {each_name}")
            continue
        if answer_by_path[bound_path] != each_expected_answer:
            scratch.all_failures.append(
                f"{label}: entry {each_name} answer is {answer_by_path[bound_path]!r}, "
                f"expected {each_expected_answer!r}"
            )


def _check_text(
    text: str,
    expect: JsonObject,
    contains_key: str,
    excludes_key: str,
    label: str,
    scratch: _Scratch,
) -> None:
    for each_needle in expect.get(contains_key, []):
        if each_needle not in text:
            scratch.all_failures.append(f"{label}: text lacks {each_needle!r}")
    for each_needle in expect.get(excludes_key, []):
        if each_needle in text:
            scratch.all_failures.append(f"{label}: text holds {each_needle!r}")


def _play_refusal(event: JsonObject, label: str, scratch: _Scratch) -> None:
    refusal_fields = _substituted(event[REFUSAL_EVENT_KEY], scratch)
    if not isinstance(refusal_fields, dict):
        raise CaseFileInvalid(f"{label}: refusal must be an object")
    session_id = str(refusal_fields.get("session_id", MAIN_SESSION_ID))
    scratch.tool_use_counter += 1
    payload: JsonObject = {
        "session_id": session_id,
        "transcript_path": str(scratch.transcript_path),
        "cwd": str(scratch.root),
        "permission_mode": PERMISSION_MODE,
        "hook_event_name": PERMISSION_DENIED_EVENT_NAME,
        "tool_use_id": f"toolu_refused_{scratch.tool_use_counter}",
        **refusal_fields,
    }
    before_paths = set(read_ledger_answers(scratch.config_directory, session_id))
    hook_run = _run_hook(scratch.refusal_hook, payload, _hook_environment(event, scratch), scratch)
    if hook_run.exit_code is None:
        scratch.all_errors.append(f"{label}: refusal hook missing at {scratch.refusal_hook}")
        return
    parsed_stdout = _parsed_stdout(hook_run)
    if hook_run.exit_code != 0 or parsed_stdout is None:
        scratch.all_errors.append(
            f"{label}: refusal hook exit {hook_run.exit_code}, stdout {hook_run.stdout[:200]!r}"
        )
        return
    all_new_paths = sorted(
        set(read_ledger_answers(scratch.config_directory, session_id)) - before_paths
    )
    if "name" in event and len(all_new_paths) == 1:
        scratch.ledger_path_by_name[str(event["name"])] = all_new_paths[0]
    expect = _substituted(event.get("expect", {}), scratch)
    if not isinstance(expect, dict):
        raise CaseFileInvalid(f"{label}: expect must be an object")
    if "creates_entry" in expect and bool(all_new_paths) != expect["creates_entry"]:
        scratch.all_failures.append(f"{label}: created {len(all_new_paths)} ledger entries")
    if "name" in event and expect.get("creates_entry", True) and len(all_new_paths) != 1:
        scratch.all_failures.append(
            f"{label}: expected one new ledger entry named {event['name']}, found {len(all_new_paths)}"
        )
    hook_specific_output = parsed_stdout.get("hookSpecificOutput")
    context_text = ""
    if isinstance(hook_specific_output, dict):
        context_text = str(hook_specific_output.get("additionalContext", ""))
    _check_text(context_text, expect, "context_contains", "context_excludes", label, scratch)
    if "stdout_equals_today" in expect:
        today_stdout = scratch.all_today_outputs[str(expect["stdout_equals_today"])]
        if hook_run.stdout != today_stdout:
            scratch.all_failures.append(
                f"{label}: stdout differs from today's output {expect['stdout_equals_today']}"
            )
    _check_ledger(expect, session_id, label, scratch)


def _play_stop(event: JsonObject, label: str, scratch: _Scratch) -> None:
    stop_fields = _substituted(event[STOP_EVENT_KEY], scratch)
    if not isinstance(stop_fields, dict):
        raise CaseFileInvalid(f"{label}: stop must be an object")
    session_id = str(stop_fields.get("session_id", MAIN_SESSION_ID))
    payload: JsonObject = {
        "session_id": session_id,
        "transcript_path": str(scratch.transcript_path),
        "cwd": str(scratch.root),
        "permission_mode": PERMISSION_MODE,
        "hook_event_name": STOP_EVENT_NAME,
        "stop_hook_active": False,
        **stop_fields,
    }
    hook_run = _run_hook(scratch.stop_hook, payload, _hook_environment(event, scratch), scratch)
    if hook_run.exit_code is None:
        scratch.all_errors.append(f"{label}: Stop gate missing at {scratch.stop_hook}")
        return
    parsed_stdout = _parsed_stdout(hook_run)
    is_held = parsed_stdout is not None and parsed_stdout.get("decision") == BLOCK_DECISION
    hold_reason = parsed_stdout.get("reason", "") if parsed_stdout else ""
    is_broken = (
        parsed_stdout is None
        or hook_run.exit_code not in ALL_STOP_EXIT_CODES
        or (hook_run.exit_code == HOLD_EXIT_CODE and not is_held)
        or not isinstance(hold_reason, str)
    )
    if is_broken:
        scratch.all_errors.append(
            f"{label}: Stop gate exit {hook_run.exit_code}, stdout {hook_run.stdout[:200]!r}"
        )
        return
    expect = _substituted(event.get("expect", {}), scratch)
    if not isinstance(expect, dict):
        raise CaseFileInvalid(f"{label}: expect must be an object")
    if "held" in expect and is_held != expect["held"]:
        scratch.all_failures.append(f"{label}: turn {'held' if is_held else 'ended'}")
    if expect.get("stdout_empty") and hook_run.stdout.strip():
        scratch.all_failures.append(f"{label}: Stop gate printed {hook_run.stdout[:120]!r}")
    _check_text(str(hold_reason), expect, "reason_contains", "reason_excludes", label, scratch)
    count_rule = expect.get("reason_holds_count_of")
    if isinstance(count_rule, dict):
        all_candidate_texts = count_rule.get("texts", [])
        found_count = sum(1 for each_text in all_candidate_texts if each_text in str(hold_reason))
        if found_count != count_rule.get("count"):
            scratch.all_failures.append(
                f"{label}: hold holds {found_count} of the listed texts, expected {count_rule.get('count')}"
            )
    _check_ledger(expect, session_id, label, scratch)


def _timestamp_fields(event: JsonObject) -> JsonObject:
    if "timestamp" not in event:
        return {"timestamp": datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)}
    if event["timestamp"] is None:
        return {}
    return {"timestamp": event["timestamp"]}


def transcript_records_for(
    event: JsonObject, tool_use_id: str, session_id: str
) -> list[JsonObject]:
    """Return the two transcript records one transcript event appends.

    ::

        {"transcript": "ask", "questions": [{"question": "Q", "answer": "Allow it"}]}
            -> assistant AskUserQuestion call, user result with answers {"Q": "Allow it"}
        {"transcript": "bash", "command": "ls"}  -> assistant Bash call, user result "ok"
        {"transcript": "card", "tool": "mcp__x", "question": "Q"} -> card call, user result

    The record shape follows an answered AskUserQuestion read from a session
    transcript: ``toolUseResult`` holds ``questions`` and ``answers``.

    Args:
        event: The transcript event from the case file.
        tool_use_id: The id that ties the call to its result.
        session_id: The session the records belong to.

    Returns:
        The assistant call record and the user result record.
    """
    transcript_kind = event[TRANSCRIPT_EVENT_KEY]
    timestamp_fields = _timestamp_fields(event)
    tool_result_block: JsonObject = {"type": "tool_result", "tool_use_id": tool_use_id}
    result_record: JsonObject = {"type": "user", "sessionId": session_id, **timestamp_fields}
    if transcript_kind == ASK_TRANSCRIPT_KIND:
        all_question_entries = event["questions"]
        if not isinstance(all_question_entries, list):
            raise CaseFileInvalid("ask questions must be a list")
        all_questions = [
            {
                "question": each_entry["question"],
                "header": each_entry.get("header", DEFAULT_QUESTION_HEADER),
                "multiSelect": False,
                "options": [dict(each_option) for each_option in ALL_QUESTION_OPTIONS],
            }
            for each_entry in all_question_entries
        ]
        tool_name, tool_input = ASK_TOOL_NAME, {"questions": all_questions}
        if event.get("error"):
            tool_result_block.update({"content": ERRORED_RESULT_CONTENT, "is_error": True})
            result_record["toolUseResult"] = ERRORED_TOOL_USE_RESULT
        else:
            answer_by_question = {
                each_entry["question"]: each_entry["answer"] for each_entry in all_question_entries
            }
            pairs_text = ANSWER_PAIR_SEPARATOR.join(
                f'"{each_question}"="{each_answer}"'
                for each_question, each_answer in answer_by_question.items()
            )
            tool_result_block["content"] = ANSWERED_RESULT_TEMPLATE.format(pairs=pairs_text)
            result_record["toolUseResult"] = {
                "questions": all_questions,
                "answers": answer_by_question,
            }
    elif transcript_kind == BASH_TRANSCRIPT_KIND:
        tool_name, tool_input = (
            BASH_TOOL_NAME,
            {"command": event["command"], "description": "Run a step"},
        )
        tool_result_block["content"] = BASH_RESULT_TEXT
        result_record["toolUseResult"] = {
            "stdout": BASH_RESULT_TEXT,
            "stderr": "",
            "interrupted": False,
            "isImage": False,
        }
    elif transcript_kind == CARD_TRANSCRIPT_KIND:
        tool_name, tool_input = (
            str(event["tool"]),
            {
                "question": event["question"],
                "options": [each_option["label"] for each_option in ALL_QUESTION_OPTIONS],
            },
        )
        tool_result_block["content"] = CARD_RESULT_TEXT
        result_record["toolUseResult"] = CARD_RESULT_TEXT
    else:
        raise CaseFileInvalid(f"unknown transcript kind {transcript_kind!r}")
    call_record: JsonObject = {
        "type": "assistant",
        "sessionId": session_id,
        **timestamp_fields,
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": tool_input}
            ],
        },
    }
    result_record["message"] = {"role": "user", "content": [tool_result_block]}
    return [call_record, result_record]


def _play_transcript(event: JsonObject, scratch: _Scratch) -> None:
    scratch.tool_use_counter += 1
    resolved_event = _substituted(event, scratch)
    if not isinstance(resolved_event, dict):
        raise CaseFileInvalid("transcript event must be an object")
    all_records = transcript_records_for(
        resolved_event, f"toolu_case_{scratch.tool_use_counter}", MAIN_SESSION_ID
    )
    with scratch.transcript_path.open("a", encoding="utf-8") as transcript_file:
        for each_record in all_records:
            transcript_file.write(json.dumps(each_record) + "\n")


def _validate_case(case: JsonObject) -> None:
    case_id = case.get("id")
    if case.get("kind") not in ALL_CASE_KINDS:
        raise CaseFileInvalid(f"{case_id}: kind must be one of {ALL_CASE_KINDS}")
    all_events = case.get("events")
    if not isinstance(all_events, list) or not all_events:
        raise CaseFileInvalid(f"{case_id}: events must be a non-empty list")
    for each_event in all_events:
        expect_keys = set(each_event.get("expect", {}))
        if REFUSAL_EVENT_KEY in each_event:
            unknown_keys = expect_keys - ALL_REFUSAL_EXPECT_KEYS
        elif STOP_EVENT_KEY in each_event:
            unknown_keys = expect_keys - ALL_STOP_EXPECT_KEYS
        elif TRANSCRIPT_EVENT_KEY in each_event:
            unknown_keys = expect_keys
        else:
            raise CaseFileInvalid(f"{case_id}: event has no refusal, stop or transcript key")
        if unknown_keys:
            raise CaseFileInvalid(f"{case_id}: unknown expect keys {sorted(unknown_keys)}")


def _write_rule_repository(scratch_root: Path) -> None:
    """Write the scratch agent-channels checkout and its rule worktree.

    ::

        agent-channels/.git/HEAD                       on claude/auto-mode-rule-own-branch-force-push
        agent-channels/setup/add_auto_mode_rule.py
        agent-channels/.git/worktrees/agent-channels-rule/{HEAD,commondir,gitdir}
        agent-channels-rule/.git                       "gitdir: <the folder above>"

    Args:
        scratch_root: The case's scratch home.
    """
    repository_root = scratch_root / RULE_REPOSITORY_NAME
    worktree_git_directory = repository_root / WORKTREE_GIT_RELATIVE_PATH
    worktree_git_directory.mkdir(parents=True)
    (repository_root / SCRATCH_GIT_NAME / "HEAD").write_text(SCRATCH_HEAD_TEXT, encoding="utf-8")
    (worktree_git_directory / "HEAD").write_text(SCRATCH_HEAD_TEXT, encoding="utf-8")
    (worktree_git_directory / "commondir").write_text(
        WORKTREE_COMMON_DIRECTORY_TEXT, encoding="utf-8"
    )
    rule_tool_path = repository_root / RULE_TOOL_RELATIVE_PATH
    rule_tool_path.parent.mkdir(parents=True)
    rule_tool_path.write_text(RULE_TOOL_TEXT, encoding="utf-8")
    worktree_directory = scratch_root / RULE_WORKTREE_NAME
    worktree_directory.mkdir()
    (worktree_directory / SCRATCH_GIT_NAME).write_text(
        GIT_FILE_TEMPLATE.format(git_directory=worktree_git_directory), encoding="utf-8"
    )
    (worktree_git_directory / WORKTREE_BACK_POINTER_NAME).write_text(
        f"{worktree_directory / SCRATCH_GIT_NAME}\n", encoding="utf-8"
    )


def run_case(
    case: JsonObject, refusal_hook: Path, stop_hook: Path, all_today_outputs: dict[str, str]
) -> CaseOutcome:
    """Play one case in a fresh scratch home and grade it.

    Args:
        case: One entry of the case file's ``cases`` list.
        refusal_hook: The PermissionDenied hook script.
        stop_hook: The Stop gate script.
        all_today_outputs: The stored stdout of today's refusal hook, by name.

    Returns:
        The verdict and the problems found.
    """
    _validate_case(case)
    scratch_root = Path(tempfile.mkdtemp(prefix="auto-mode-flow-case-"))
    try:
        scratch = _Scratch(scratch_root, refusal_hook, stop_hook, all_today_outputs)
        scratch.config_directory.mkdir()
        scratch.playbook_path.parent.mkdir(parents=True)
        scratch.playbook_path.write_text(PLAYBOOK_TEXT, encoding="utf-8")
        _write_rule_repository(scratch_root)
        scratch.transcript_path.write_text("", encoding="utf-8")
        for each_index, each_event in enumerate(case["events"], start=1):
            label = f"event {each_index}"
            if REFUSAL_EVENT_KEY in each_event:
                _play_refusal(each_event, label, scratch)
            elif STOP_EVENT_KEY in each_event:
                _play_stop(each_event, label, scratch)
            else:
                _play_transcript(each_event, scratch)
    finally:
        force_rmtree(str(scratch_root))
    if scratch.all_errors:
        verdict = ERROR_VERDICT
    elif scratch.all_failures:
        verdict = FAIL_VERDICT
    else:
        verdict = PASS_VERDICT
    return CaseOutcome(
        case_id=str(case["id"]),
        kind=str(case["kind"]),
        verdict=verdict,
        all_problems=tuple(scratch.all_errors + scratch.all_failures),
    )


def load_case_file(case_file_path: Path) -> JsonObject:
    """Read the case file.

    Args:
        case_file_path: Path to ``auto_mode_rule_flow_cases.json``.

    Returns:
        The parsed case file, with ``cases`` and ``today_outputs``.
    """
    parsed_file = json.loads(case_file_path.read_text(encoding="utf-8"))
    if not isinstance(parsed_file, dict) or not isinstance(parsed_file.get("cases"), list):
        raise CaseFileInvalid(f"{case_file_path} has no cases list")
    return parsed_file


def run_all_cases(
    case_file_path: Path,
    refusal_hook: Path,
    stop_hook: Path,
    all_case_prefixes: tuple[str, ...],
) -> list[CaseOutcome]:
    """Run every case, or the cases whose id starts with one of the prefixes.

    Args:
        case_file_path: Path to the case file.
        refusal_hook: The PermissionDenied hook script.
        stop_hook: The Stop gate script.
        all_case_prefixes: Id prefixes such as ``("R", "N3")``; empty runs every case.

    Returns:
        One outcome per case, in case file order.
    """
    case_file = load_case_file(case_file_path)
    all_today_outputs = case_file.get("today_outputs", {})
    if not isinstance(all_today_outputs, dict):
        raise CaseFileInvalid("today_outputs must be an object")
    return [
        run_case(each_case, refusal_hook, stop_hook, all_today_outputs)
        for each_case in case_file["cases"]
        if not all_case_prefixes or str(each_case["id"]).startswith(all_case_prefixes)
    ]


def score_summary(all_outcomes: list[CaseOutcome]) -> dict[str, int]:
    """Count passes per kind and errors.

    ::

        R1 should act pass, R8 should stay quiet fail, Q1 should act error
            -> should_act_passed 1 of 2, should_stay_quiet_passed 0 of 1, errors 1

    Args:
        all_outcomes: The outcomes from ``run_all_cases``.

    Returns:
        ``should_act_passed``, ``should_act_total``, ``should_stay_quiet_passed``,
        ``should_stay_quiet_total`` and ``errors``.
    """
    return {
        "should_act_passed": sum(
            1
            for each in all_outcomes
            if each.kind == SHOULD_ACT_KIND and each.verdict == PASS_VERDICT
        ),
        "should_act_total": sum(1 for each in all_outcomes if each.kind == SHOULD_ACT_KIND),
        "should_stay_quiet_passed": sum(
            1
            for each in all_outcomes
            if each.kind == SHOULD_STAY_QUIET_KIND and each.verdict == PASS_VERDICT
        ),
        "should_stay_quiet_total": sum(
            1 for each in all_outcomes if each.kind == SHOULD_STAY_QUIET_KIND
        ),
        "errors": sum(1 for each in all_outcomes if each.verdict == ERROR_VERDICT),
    }


def calibration_problems(case_file_path: Path) -> list[str]:
    """Score the cases against the two stub hooks and name each miscalibration.

    ::

        stub that never acts       -> must pass no ``should act`` case
        stub that records and holds -> must pass no ``should stay quiet`` case
        either stub                -> must cause no error

    Args:
        case_file_path: Path to the case file.

    Returns:
        One line per calibration that does not hold; empty when both hold.
    """
    eval_directory = Path(__file__).resolve().parent
    allow_stub = eval_directory / ALLOW_STUB_FILE_NAME
    hold_stub = eval_directory / HOLD_STUB_FILE_NAME
    allow_summary = score_summary(run_all_cases(case_file_path, allow_stub, allow_stub, ()))
    hold_summary = score_summary(run_all_cases(case_file_path, hold_stub, hold_stub, ()))
    all_checks = (
        (ALLOW_STUB_FILE_NAME, SHOULD_ACT_PASSED_KEY, allow_summary),
        (HOLD_STUB_FILE_NAME, SHOULD_STAY_QUIET_PASSED_KEY, hold_summary),
    )
    all_problems: list[str] = []
    for each_stub_name, each_passed_key, each_summary in all_checks:
        if each_summary[each_passed_key] or each_summary[ERRORS_KEY]:
            all_problems.append(
                CALIBRATION_PROBLEM_TEMPLATE.format(stub_name=each_stub_name, **each_summary)
            )
    return all_problems


def report_text_for(
    all_outcomes: list[CaseOutcome], all_counts: dict[str, int], is_verbose: bool
) -> str:
    """Return the report the runner prints: one line per case, then the score.

    ::

        R1    should act        pass
              event 1: created 0 ledger entries     (only when verbose)
        should act passed 1 of 1; should stay quiet passed 0 of 0; errors 0

    Args:
        all_outcomes: The graded cases, in run order.
        all_counts: The counts from ``score_summary``.
        is_verbose: Whether to add each problem line under its case.

    Returns:
        The report text, each line ending in a newline.
    """
    all_lines: list[str] = []
    for each_outcome in all_outcomes:
        all_lines.append(
            f"{each_outcome.case_id:5} {each_outcome.kind:17} {each_outcome.verdict}"
        )
        if is_verbose:
            all_lines.extend(
                PROBLEM_LINE_INDENT + each_problem for each_problem in each_outcome.all_problems
            )
    all_lines.append(SUMMARY_LINE_TEMPLATE.format(**all_counts))
    all_lines.append(ERROR_RULE_LINE)
    return "".join(each_line + "\n" for each_line in all_lines)


def main() -> int:
    hooks_root = Path(_hooks_root_directory)
    parser = argparse.ArgumentParser(description="Run the auto mode rule flow cases.")
    parser.add_argument(
        "--refusal-hook", type=Path, default=hooks_root / DEFAULT_REFUSAL_HOOK_RELATIVE_PATH
    )
    parser.add_argument(
        "--stop-hook", type=Path, default=hooks_root / DEFAULT_STOP_HOOK_RELATIVE_PATH
    )
    parser.add_argument(
        "--cases", type=Path, default=Path(__file__).resolve().parent / CASE_FILE_NAME
    )
    parser.add_argument("--only", default="", help="comma-separated case id prefixes, such as R,N3")
    parser.add_argument("--verbose", action="store_true", help="print each problem line")
    parser.add_argument(
        "--calibrate", action="store_true", help="score the cases against both stub hooks"
    )
    arguments = parser.parse_args()
    if arguments.calibrate:
        all_problems = calibration_problems(arguments.cases)
        sys.stdout.write("".join(each_line + "\n" for each_line in all_problems or [CALIBRATED_LINE]))
        sys.stdout.flush()
        return 1 if all_problems else 0
    all_case_prefixes = tuple(each for each in arguments.only.split(",") if each)
    all_outcomes = run_all_cases(
        arguments.cases,
        arguments.refusal_hook.resolve(),
        arguments.stop_hook.resolve(),
        all_case_prefixes,
    )
    summary = score_summary(all_outcomes)
    sys.stdout.write(report_text_for(all_outcomes, summary, arguments.verbose))
    sys.stdout.flush()
    is_all_passed = summary["should_act_passed"] + summary["should_stay_quiet_passed"] == len(
        all_outcomes
    )
    return 0 if is_all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
