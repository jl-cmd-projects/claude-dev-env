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
    output = io.StringIO()

    assert main(["plan"], output) == 0
    assert json.loads(output.getvalue()) == {
        "runtime": "other",
        "model": "deferred",
        "profile": "deferred",
    }
    assert output.getvalue().endswith("\n")


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(SystemExit) as result:
        main(["unknown"], io.StringIO())

    assert result.value.code == 2
