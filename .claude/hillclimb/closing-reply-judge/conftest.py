"""Put the eval flow and the hooks folders on the import path, and give the tests a stub claude and case rows."""

import json
import os
import stat
import sys
from pathlib import Path

import pytest

flow_directory = Path(__file__).resolve().parent
hooks_directory = flow_directory.parents[2] / "packages" / "claude-dev-env" / "hooks"

for each_import_root in (flow_directory, hooks_directory, hooks_directory / "blocking"):
    if str(each_import_root) not in sys.path:
        sys.path.append(str(each_import_root))

STUB_TEMPLATE = """#!{python}
import json, os, sys
sys.stdin.read()
state = os.environ["RUN_STUB_STATE"]
with open(state + ".calls", "a") as calls_file:
    calls_file.write(" ".join(sys.argv[1:]) + "\\n")
answer = json.load(open(state))
if answer.get("exit_code"):
    sys.exit(answer["exit_code"])
print(json.dumps(answer["stdout"]))
"""
PROMISE = "I'll send the benchmark table tomorrow."
REPLY = "The cache rewrite is pushed. " + PROMISE


@pytest.fixture
def promise_text() -> str:
    return PROMISE


@pytest.fixture
def make_case():
    def build(case_id: str, label: str, reply: str = REPLY, prompt: str = "Rewrite the cache.") -> dict:
        return {
            "id": case_id,
            "set": case_id.split("/")[0],
            "label": label,
            "prompt": prompt,
            "reply": reply,
            "question_tool": False,
            "incident1_row": False,
        }

    return build


@pytest.fixture
def verdict_text():
    def build(promise_span: str = "", list_span: str = "") -> str:
        return json.dumps(
            {
                "promised_report": bool(promise_span),
                "promise_span": promise_span,
                "decisions_as_list": bool(list_span),
                "list_span": list_span,
            }
        )

    return build


@pytest.fixture
def stub_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    stub_folder = tmp_path / "bin"
    stub_folder.mkdir()
    stub_path = stub_folder / "claude"
    stub_path.write_text(STUB_TEMPLATE.format(python=sys.executable), encoding="utf-8")
    stub_path.chmod(stub_path.stat().st_mode | stat.S_IEXEC)
    state_path = tmp_path / "stub.json"
    monkeypatch.setenv("RUN_STUB_STATE", str(state_path))
    monkeypatch.setenv("PATH", f"{stub_folder}{os.pathsep}{os.environ['PATH']}")

    def answer(result: str | None = None, exit_code: int = 0, **outer: object) -> Path:
        stdout = {"result": result, "total_cost_usd": 0.0004, "modelUsage": {"claude-haiku-4-5": {}}, **outer}
        state_path.write_text(json.dumps({"stdout": stdout, "exit_code": exit_code}), encoding="utf-8")
        return stub_path

    return answer
