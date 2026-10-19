import io
import json
from pathlib import Path
import sys

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from tools.efficient_review import main


def test_plan_command_prints_one_deferred_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
    plan_stream = io.StringIO()

    assert main(["plan"], plan_stream) == 0
    assert json.loads(plan_stream.getvalue()) == {
        "runtime": "other",
        "model": "deferred",
        "profile": "deferred",
    }
    assert plan_stream.getvalue().endswith("\n")


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["unknown"], io.StringIO())

    assert exit_info.value.code == 2
