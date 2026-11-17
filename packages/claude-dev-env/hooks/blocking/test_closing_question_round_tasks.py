import time
from pathlib import Path

import pytest

from closing_question_round_tasks import declared_tasks_reason
from hooks_constants.closing_question_round_gate_constants import (
    IN_PROGRESS_TASKS_REASON_LEAD,
)
from test_closing_question_round_gate import SESSION_ID
from test_closing_question_round_gate_tasks import (
    MAIN_GOAL_SUBJECT,
    write_task_store,
)
from test_closing_question_round_gate_work import DECLARATION


def test_should_name_each_in_progress_task_only_beside_a_declaration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)
    write_task_store(
        tmp_path,
        [
            {"id": "3", "subject": MAIN_GOAL_SUBJECT, "status": "in_progress"},
            {"id": "4", "subject": "P2 counts", "status": "pending"},
        ],
    )
    all_hook_input_fields: dict[str, object] = {"session_id": SESSION_ID}
    far_deadline_at = time.monotonic() + 60
    reason = declared_tasks_reason(all_hook_input_fields, [f"Done.\n\n{DECLARATION}"], far_deadline_at)
    assert reason is not None
    assert reason.startswith(IN_PROGRESS_TASKS_REASON_LEAD)
    assert f'#3 "{MAIN_GOAL_SUBJECT}"' in reason
    assert "P2 counts" not in reason
    assert declared_tasks_reason(all_hook_input_fields, ["Done."], far_deadline_at) is None
    assert declared_tasks_reason(all_hook_input_fields, [], far_deadline_at) is None
