"""A replayed session on disk: its transcript, its task store, its home, and a stand-in judge.

::

    session = ReplaySession(folder, all_tasks)
    session.add_user_text("Ship it.", "human")
    session.add_tool_calls(["Bash"])
    session.add_reply("Done.")
    session.stop_reasons(hooks_directory, "Done.", False)   -> ["This turn worked on ..."]
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

from repeated_footer_eval_support.config.constants import (
    ALL_HOME_ENVIRONMENT_VARIABLES,
    ALL_REMOVED_ENVIRONMENT_VARIABLES,
    ALL_STOP_GATE_FILE_NAMES,
    ALL_STOP_PAYLOAD_FIELDS,
    ASSISTANT_RECORD_TYPE,
    BLOCKING_DIRECTORY_NAME,
    CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE,
    CLAUDE_HOME_DIRECTORY_NAME,
    CONTENT_KEY,
    HOLD_EXIT_CODE,
    HOME_DIRECTORY_NAME,
    HOOK_TIMEOUT_SECONDS,
    INTERACTIVE_SESSION_ATTENDED_TEXT,
    LAST_ASSISTANT_MESSAGE_KEY,
    MESSAGE_KEY,
    PATH_ENVIRONMENT_VARIABLE,
    RECORD_SEPARATOR,
    RECORD_TYPE_KEY,
    ROLE_KEY,
    SESSION_ATTENDED_ENVIRONMENT_VARIABLE,
    SESSION_ID,
    STOP_HOOK_ACTIVE_KEY,
    STOP_REASON_KEY,
    STUB_BIN_DIRECTORY_NAME,
    STUB_JUDGE_FILE_NAME,
    STUB_JUDGE_MODE,
    STUB_JUDGE_SOURCE,
    TASK_FILE_SUFFIX,
    TASK_ID_KEY,
    TASKS_DIRECTORY_NAME,
    TEMPORARY_DIRECTORY_ENVIRONMENT_VARIABLE,
    TEMPORARY_DIRECTORY_NAME,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TOOL_ID_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_RESULT_TEXT,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_KEY,
    TOOL_USE_ID_TEMPLATE,
    TRANSCRIPT_FILE_NAME,
    TRANSCRIPT_PATH_KEY,
    TURN_ORIGIN_KEY,
    USER_RECORD_TYPE,
    UTF8_ENCODING,
    UUID_KEY,
    UUID_TEMPLATE,
)


def write_task_store(claude_home: Path, all_tasks: list[dict[str, object]]) -> None:
    """Write each task to the store the gates read, ``<claude home>/tasks/<session id>/<id>.json``.

    Args:
        claude_home: The session's Claude home folder.
        all_tasks: The task entries, each with its ``id``.
    """
    task_directory = claude_home / TASKS_DIRECTORY_NAME / SESSION_ID
    task_directory.mkdir(parents=True)
    for each_task in all_tasks:
        (task_directory / f"{each_task[TASK_ID_KEY]}{TASK_FILE_SUFFIX}").write_text(
            json.dumps(each_task), encoding=UTF8_ENCODING
        )


def write_stub_judge(session_directory: Path) -> Path:
    """Write the stand-in ``claude`` that plays the reply judge and return its folder.

    Args:
        session_directory: The session folder.

    Returns:
        The folder to put first on PATH.
    """
    stub_directory = session_directory / STUB_BIN_DIRECTORY_NAME
    stub_directory.mkdir()
    stub_judge = stub_directory / STUB_JUDGE_FILE_NAME
    stub_judge.write_text(STUB_JUDGE_SOURCE, encoding=UTF8_ENCODING)
    stub_judge.chmod(STUB_JUDGE_MODE)
    return stub_directory


def gate_environment(
    session_directory: Path, claude_home: Path, stub_directory: Path
) -> dict[str, str]:
    """Return an interactive session's environment with its home, temp folder, and judge in the session folder.

    Args:
        session_directory: The session folder.
        claude_home: The session's Claude home folder.
        stub_directory: The folder that holds the stand-in judge.

    Returns:
        The environment each gate runs in.
    """
    temporary_directory = session_directory / TEMPORARY_DIRECTORY_NAME
    temporary_directory.mkdir()
    all_variables = {
        each_name: each_setting
        for each_name, each_setting in os.environ.items()
        if each_name not in ALL_REMOVED_ENVIRONMENT_VARIABLES
    }
    all_variables.update(
        dict.fromkeys(ALL_HOME_ENVIRONMENT_VARIABLES, str(claude_home.parent))
    )
    all_variables[CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE] = str(claude_home)
    all_variables[SESSION_ATTENDED_ENVIRONMENT_VARIABLE] = (
        INTERACTIVE_SESSION_ATTENDED_TEXT
    )
    all_variables[TEMPORARY_DIRECTORY_ENVIRONMENT_VARIABLE] = str(temporary_directory)
    all_variables[PATH_ENVIRONMENT_VARIABLE] = os.pathsep.join(
        [str(stub_directory), os.environ.get(PATH_ENVIRONMENT_VARIABLE, "")]
    )
    return all_variables


def _message_record(
    record_type: str, all_blocks: list[dict[str, object]] | str
) -> dict[str, object]:
    return {
        RECORD_TYPE_KEY: record_type,
        MESSAGE_KEY: {ROLE_KEY: record_type, CONTENT_KEY: all_blocks},
    }


class ReplaySession:
    """A session folder the gates read; add_user_text, add_tool_calls, and add_reply grow its transcript, and stop_reasons runs the gates."""

    def __init__(
        self, session_directory: Path, all_tasks: list[dict[str, object]]
    ) -> None:
        self.session_directory = session_directory
        self.transcript_path = session_directory / TRANSCRIPT_FILE_NAME
        self.all_records: list[dict[str, object]] = []
        self.record_numbers = itertools.count(1)
        claude_home = (
            session_directory / HOME_DIRECTORY_NAME / CLAUDE_HOME_DIRECTORY_NAME
        )
        write_task_store(claude_home, all_tasks)
        self.environment = gate_environment(
            session_directory, claude_home, write_stub_judge(session_directory)
        )

    def _append(self, all_record_fields: dict[str, object]) -> None:
        all_record_fields[UUID_KEY] = UUID_TEMPLATE.format(
            number=next(self.record_numbers)
        )
        self.all_records.append(all_record_fields)

    def add_user_text(self, text: str, turn_origin: str | None) -> None:
        """Add a user record.

        Args:
            text: A typed prompt, a notification, or stop feedback.
            turn_origin: The record's ``turnOrigin``, or None for stop feedback.
        """
        all_record_fields = _message_record(USER_RECORD_TYPE, text)
        if turn_origin is not None:
            all_record_fields[TURN_ORIGIN_KEY] = turn_origin
        self._append(all_record_fields)

    def add_tool_calls(self, all_tool_names: list[str]) -> None:
        """Add one assistant tool call and its result for each tool name.

        Args:
            all_tool_names: The tools called, in order.
        """
        for each_tool_name in all_tool_names:
            tool_use_id = TOOL_USE_ID_TEMPLATE.format(number=len(self.all_records))
            tool_call_block = {
                RECORD_TYPE_KEY: TOOL_USE_BLOCK_TYPE,
                TOOL_ID_KEY: tool_use_id,
                TOOL_NAME_KEY: each_tool_name,
                TOOL_INPUT_KEY: {},
            }
            tool_answer_block = {
                RECORD_TYPE_KEY: TOOL_RESULT_BLOCK_TYPE,
                TOOL_USE_ID_KEY: tool_use_id,
                CONTENT_KEY: TOOL_RESULT_TEXT,
            }
            self._append(_message_record(ASSISTANT_RECORD_TYPE, [tool_call_block]))
            self._append(_message_record(USER_RECORD_TYPE, [tool_answer_block]))

    def add_reply(self, reply_text: str) -> None:
        """Add an assistant text record.

        Args:
            reply_text: The reply the user sees.
        """
        self._append(
            _message_record(
                ASSISTANT_RECORD_TYPE,
                [{RECORD_TYPE_KEY: TEXT_BLOCK_TYPE, TEXT_KEY: reply_text}],
            )
        )

    def stop_reasons(
        self, hooks_directory: Path, reply_text: str, is_held_stop: bool
    ) -> list[str]:
        """Run each Stop gate on the session as Claude Code does and return the reason of each hold.

        Args:
            hooks_directory: The ``hooks`` folder whose gates run.
            reply_text: The closing reply, sent as ``last_assistant_message``.
            is_held_stop: Whether a gate already held this turn, sent as ``stop_hook_active``.

        Returns:
            One reason per gate that held, in gate order.
        """
        self.transcript_path.write_text(
            RECORD_SEPARATOR.join(
                json.dumps(each_record) for each_record in self.all_records
            ),
            encoding=UTF8_ENCODING,
        )
        stop_payload = json.dumps(
            {
                **ALL_STOP_PAYLOAD_FIELDS,
                TRANSCRIPT_PATH_KEY: str(self.transcript_path),
                STOP_HOOK_ACTIVE_KEY: is_held_stop,
                LAST_ASSISTANT_MESSAGE_KEY: reply_text,
            }
        )
        all_runs = [
            subprocess.run(
                [
                    sys.executable,
                    str(hooks_directory / BLOCKING_DIRECTORY_NAME / each_gate_name),
                ],
                input=stop_payload,
                capture_output=True,
                text=True,
                env=self.environment,
                cwd=self.session_directory,
                timeout=HOOK_TIMEOUT_SECONDS,
                check=False,
            )
            for each_gate_name in ALL_STOP_GATE_FILE_NAMES
        ]
        return [
            str(json.loads(each_run.stdout).get(STOP_REASON_KEY, ""))
            for each_run in all_runs
            if each_run.returncode == HOLD_EXIT_CODE
        ]
