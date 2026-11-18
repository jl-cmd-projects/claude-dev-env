"""Integration checks for compact-session inputs and user-turn recall."""

import importlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tests.behavior.scope_drift import suite


@pytest.fixture(scope="module", autouse=True)
def pinned_commit():
    available = subprocess.run(
        ["git", "cat-file", "-e", f"{suite.BASELINE}^{{commit}}"],
        check=False,
        cwd=suite.ROOT,
        capture_output=True,
    )
    if available.returncode:
        shallow = subprocess.check_output(
            ["git", "rev-parse", "--is-shallow-repository"], cwd=suite.ROOT
        )
        if shallow.strip() == b"true":
            pytest.skip("Pinned compact-hook commit is outside the shallow checkout")
        available.check_returncode()


@pytest.fixture(scope="module")
def driver():
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(sys.modules, "suite", suite)
        return importlib.import_module("tests.behavior.scope_drift.recall_driver")


def cli(operation, case_id, arm, run):
    return subprocess.run(
        [
            sys.executable,
            str(suite.ROOT / "recall_driver.py"),
            operation,
            case_id,
            arm,
            str(run),
        ],
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("case_ids", [("seaport", "estuary"), ("lantern", "beacon")])
def test_authority_twins_share_clipped_hook_context(
    driver, tmp_path: Path, case_ids
) -> None:
    cases = driver.read_cases()
    first, second = (cases[case_id] for case_id in case_ids)
    assert first["turns"] == second["turns"]
    assert first["files"] == second["files"]
    assert first["summary"] == second["summary"]
    assert first["original"] != second["original"]
    assert first["expect"] != second["expect"]

    pinned = suite.instructions("baseline")
    contexts = []
    for case in (first, second):
        baseline = driver.prepare(case, "baseline", tmp_path / f"{case['id']} baseline")
        candidate = driver.prepare(
            case, "candidate", tmp_path / f"{case['id']} candidate"
        )
        assert baseline["clipped"] and candidate["clipped"]
        common = Path(baseline["context"]).read_bytes()
        assert b"more characters left out" in common
        contexts.append(common)

        augmented = Path(candidate["context"]).read_bytes()
        assert augmented.startswith(common)
        hint = augmented[len(common) :].decode()
        assert "If a missing or shortened turn could affect the current task" in hint
        reader = Path(candidate["context"]).with_name("read-user-turns.py")
        assert shlex.split(hint.splitlines()[-1]) == [
            "python3",
            "-IB",
            str(reader),
            "FIRST",
            "[LAST]",
        ]
        assert (
            baseline["context_sha256"]
            == suite.digest(common)
            == candidate["hook_context_sha256"]
        )
        assert (
            candidate["context_sha256"]
            == suite.digest(augmented)
            != baseline["context_sha256"]
        )
        for prepared in (baseline, candidate):
            assert (Path(prepared["work"]) / "AGENTS.md").read_bytes() == pinned
            assert prepared["instructions_sha256"] == suite.digest(pinned)

    assert contexts[0] == contexts[1]


def test_complete_hook_context_gets_no_recall_hint(driver, tmp_path: Path) -> None:
    case = {
        "original": ["Transfer the North runbooks only."],
        "turns": ["Go ahead."],
        "files": {},
    }
    baseline = driver.prepare(case, "baseline", tmp_path / "short-a")
    candidate = driver.prepare(case, "candidate", tmp_path / "short-b")

    assert not baseline["clipped"] and not candidate["clipped"]
    plain = Path(baseline["context"]).read_bytes()
    assert b"North runbooks only" in plain
    assert b"read-user-turns.py" not in plain
    assert Path(candidate["context"]).read_bytes() == plain
    assert (
        baseline["context_sha256"] == candidate["context_sha256"] == suite.digest(plain)
    )


def test_reader_selects_full_user_messages_in_an_inclusive_range(
    driver, tmp_path: Path
) -> None:
    case = driver.read_cases()["copper"]
    prepared = driver.prepare(case, "candidate", tmp_path / "reader")
    context = Path(prepared["context"])
    assert b"earlier messages left out to fit the budget" in context.read_bytes()
    transcript = context.with_name("rollout.jsonl").read_text(encoding="utf-8")
    assert {
        json.loads(line)["payload"]["type"] for line in transcript.splitlines()
    } == {"user_message", "agent_message", "function_call_output"}
    command = [sys.executable, "-IB", str(context.with_name("read-user-turns.py"))]

    one_turn = json.loads(subprocess.check_output([*command, "2"]))
    range_of_turns = json.loads(subprocess.check_output([*command, "2", "4"]))

    assert one_turn == [{"position": 2, "text": case["original"][1]}]
    assert range_of_turns == [
        {"position": position, "text": case["original"][position - 1]}
        for position in range(2, 5)
    ]


@pytest.mark.parametrize(
    ("name", "replacement"),
    [
        ("compact-context.txt", None),
        ("compact-context.txt", b"Changed compact session context."),
        ("hooks/session/compaction_recall_prompt.py", b"Changed pinned hook source."),
    ],
)
def test_assess_rejects_missing_or_changed_session_files(
    driver, tmp_path: Path, name, replacement
) -> None:
    case = driver.read_cases()["estuary"]
    run = tmp_path / "integrity"
    driver.prepare(case, "candidate", run)
    for path, content in case["expect"].items():
        (run / "work" / path).write_bytes(content.encode())

    passed = cli("assess", case["id"], "candidate", run)
    assert passed.returncode == 0, passed.stderr.decode()
    assert json.loads(passed.stdout)["changed_session_files"] == []

    changed = run / ".session" / name
    if replacement is None:
        changed.unlink()
    else:
        changed.chmod(0o644)
        changed.write_bytes(replacement)

    failed = cli("assess", case["id"], "candidate", run)
    assert failed.returncode == 1, failed.stderr.decode()
    grade = json.loads(failed.stdout)
    assert grade["file_checks_pass"]
    assert grade["changed_session_files"] == [name]
