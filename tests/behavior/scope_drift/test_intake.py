"""Replay captured intake deliveries and compare the deterministic probe grades."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from tests.behavior.scope_drift import intake_probe, suite

if TYPE_CHECKING:
    from tests.behavior.scope_drift.intake_probe import IntakeCase


PUBLISHED_SEED = 4719
ALL_CONDITIONS = (
    ("full", "baseline", 1),
    ("partial", "baseline", 1),
    ("partial", "candidate", 1),
    ("partial", "baseline", 2),
    ("partial", "candidate", 2),
    ("clipped", "baseline", 1),
    ("clipped", "candidate", 1),
)


class _CapturedProbe(TypedDict):
    passed: bool
    source_pass: bool
    sample_data_pass: bool
    sample: bool
    heldout: bool
    generated: bool
    heldout_count: int
    generated_count: int
    seed: int


class _CapturedDelivery(TypedDict):
    case: str
    cohort: str
    arm: str
    repeat: int
    brief: str
    brief_sha256: str
    transferred_brief_sha256: str
    recipient_after_sha256: dict[str, str]
    recipient_loaded_sha256: str
    sender_loaded_sha256: str
    sender_input_sha256: str
    changes: dict[str, str | None]
    probe: _CapturedProbe


def _read_captures() -> list[_CapturedDelivery]:
    evidence = suite.ROOT / "intake-outcomes.jsonl"
    return [
        json.loads(line) for line in evidence.read_text(encoding="utf-8").splitlines()
    ]


def _delivery_key(capture: _CapturedDelivery) -> tuple[str, str, str, int]:
    return capture["case"], capture["cohort"], capture["arm"], capture["repeat"]


def _delivery_files(
    case: IntakeCase, capture: _CapturedDelivery, instructions: bytes
) -> dict[str, bytes]:
    all_files = {name: content.encode() for name, content in case["files"].items()}
    brief_name = case["brief"]
    brief = capture["brief"].encode()
    assert brief_name not in all_files and "AGENTS.md" not in all_files
    assert brief and suite.digest(brief) == capture["brief_sha256"]

    probes = case["probes"]
    program = probes["program"]
    all_program_paths = {program, probes["sample"], f"test_{program}"}
    assert capture["changes"].keys() <= all_program_paths
    for each_name, each_content in capture["changes"].items():
        if each_content is None:
            del all_files[each_name]
        else:
            all_files[each_name] = each_content.encode()
    return {**all_files, "AGENTS.md": instructions, brief_name: brief}


def _materialize(work: Path, all_files: dict[str, bytes]) -> None:
    work.mkdir()
    for each_name, each_content in all_files.items():
        path = suite.safe_file(work, each_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(each_content)


def _workspace_manifest(work: Path) -> dict[str, bytes]:
    assert not work.is_symlink() and work.is_dir()
    all_paths = list(work.rglob("*"))
    assert not any(path.is_symlink() for path in all_paths)
    return {
        path.relative_to(work).as_posix(): path.read_bytes()
        for path in all_paths
        if path.is_file()
    }


def _replay_probes(case: IntakeCase, work: Path) -> _CapturedProbe:
    grade = intake_probe.assess(case, work, PUBLISHED_SEED)
    sample = grade["sample"]
    heldout = grade["heldout"]
    generated = grade["generated"]
    assert isinstance(sample, dict)
    assert isinstance(heldout, dict)
    assert isinstance(generated, dict)
    heldout_count = grade["heldout_count"]
    generated_count = grade["generated_count"]
    seed = grade["seed"]
    assert isinstance(heldout_count, int)
    assert isinstance(generated_count, int)
    assert isinstance(seed, int)
    return {
        "passed": grade["passed"] is True,
        "source_pass": grade["source_pass"] is True,
        "sample_data_pass": grade["sample_data_pass"] is True,
        "sample": sample["passed"] is True,
        "heldout": heldout["passed"] is True,
        "generated": generated["passed"] is True,
        "heldout_count": heldout_count,
        "generated_count": generated_count,
        "seed": seed,
    }


def _replay_delivery(
    case: IntakeCase, capture: _CapturedDelivery, work: Path, instructions: bytes
) -> _CapturedProbe:
    all_files = _delivery_files(case, capture, instructions)
    _materialize(work, all_files)

    instructions_digest = suite.digest((work / "AGENTS.md").read_bytes())
    assert capture["recipient_loaded_sha256"] in (
        instructions_digest,
        instructions_digest + "\n",
    )
    assert capture["sender_loaded_sha256"] == capture["sender_input_sha256"]
    if capture["cohort"] == "full":
        assert capture["sender_input_sha256"] == instructions_digest
    brief_digest = suite.digest((work / case["brief"]).read_bytes())
    assert (
        brief_digest == capture["brief_sha256"] == capture["transferred_brief_sha256"]
    )

    grade = _replay_probes(case, work)
    assert grade == capture["probe"], _delivery_key(capture)
    manifest = _workspace_manifest(work)
    assert manifest == all_files
    all_file_digests = {
        name: suite.digest(content) for name, content in manifest.items()
    }
    assert all_file_digests == capture["recipient_after_sha256"], _delivery_key(capture)
    return grade


def test_replays_captured_intake_deliveries(tmp_path: Path) -> None:
    """Verify the durable roster, transferred bytes, and probe outcomes."""
    all_cases = intake_probe.read_cases()
    all_captures = _read_captures()
    all_expected = Counter(
        (case, cohort, arm, repeat)
        for case in all_cases
        for cohort, arm, repeat in ALL_CONDITIONS
    )
    assert Counter(map(_delivery_key, all_captures)) == all_expected
    assert len(all_captures) == 14

    instructions = suite.instructions("baseline")
    probe_totals: Counter[tuple[str, str]] = Counter()
    for each_index, each_capture in enumerate(all_captures):
        work = tmp_path / str(each_index)
        grade = _replay_delivery(
            all_cases[each_capture["case"]], each_capture, work, instructions
        )
        assert grade["sample"], _delivery_key(each_capture)
        probe_totals[each_capture["cohort"], each_capture["arm"]] += grade["passed"]
    assert probe_totals == {
        ("full", "baseline"): 2,
        ("partial", "baseline"): 4,
        ("partial", "candidate"): 4,
        ("clipped", "baseline"): 1,
        ("clipped", "candidate"): 2,
    }
