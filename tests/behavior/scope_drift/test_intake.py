"""Replay captured intake deliveries and compare the deterministic probe grades."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, NotRequired, TypedDict

import pytest

from tests.behavior.scope_drift import intake_probe, recall_driver, suite
from tests.behavior.scope_drift.config import recall as protocol

if TYPE_CHECKING:
    from tests.behavior.scope_drift.intake_probe import IntakeCase


PUBLISHED_SEED = 4719
BASELINE_INSTRUCTIONS_SHA256 = (
    "891bdb4c8d3ac3b7771ba6f653279ccf299ddb2ca0c4fd8748e2e17b71e7a11f"
)
BASELINE_HOOK_MANIFEST_SHA256 = (
    "4502d9aab8ec5e62dceed55813b1ac93fd9994239ae1fff8d77d223305e2a78c"
)
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
    sender_session_path: NotRequired[str]
    changes: dict[str, str | None]
    probe: _CapturedProbe


@dataclass(frozen=True)
class _BaselineInputs:
    instructions: bytes
    hooks_by_path: dict[str, bytes] | None


def _read_captures() -> list[_CapturedDelivery]:
    evidence = suite.ROOT / "intake-outcomes.jsonl"
    return [
        json.loads(line) for line in evidence.read_text(encoding="utf-8").splitlines()
    ]


def _checked_out_hooks(repository: Path) -> dict[str, bytes] | None:
    all_hooks = {}
    for each_name in protocol.ALL_HOOK_SOURCES:
        path = repository / protocol.HOOK_PACKAGE / each_name
        if not path.is_file():
            return None
        all_hooks[each_name] = path.read_bytes()
    all_digests = {name: suite.digest(source) for name, source in all_hooks.items()}
    manifest = json.dumps(all_digests, sort_keys=True).encode()
    if suite.digest(manifest) != BASELINE_HOOK_MANIFEST_SHA256:
        return None
    return all_hooks


@pytest.fixture(scope="module")
def baseline_inputs() -> _BaselineInputs:
    """Load pinned trial inputs or verify identical files in a shallow checkout."""
    pinned_commit = subprocess.run(
        ["git", "cat-file", "-e", f"{suite.BASELINE}^{{commit}}"],
        cwd=suite.ROOT,
        capture_output=True,
        check=False,
    )
    if pinned_commit.returncode == 0:
        return _BaselineInputs(
            suite.instructions("baseline"),
            {
                name: recall_driver._pinned_file(f"{protocol.HOOK_PACKAGE}/{name}")
                for name in protocol.ALL_HOOK_SOURCES
            },
        )

    repository_state = subprocess.check_output(
        ["git", "rev-parse", "--is-shallow-repository", "--show-toplevel"],
        cwd=suite.ROOT,
        text=True,
    )
    shallow, repository = repository_state.splitlines()
    if shallow != "true":
        pinned_commit.check_returncode()
    prompt = Path(repository) / suite.PROMPT
    if prompt.is_file():
        instructions = prompt.read_bytes()
        if suite.digest(instructions) == BASELINE_INSTRUCTIONS_SHA256:
            return _BaselineInputs(instructions, _checked_out_hooks(Path(repository)))
    pytest.skip(
        "The pinned Sol prompt is outside this shallow checkout and the checked-out "
        "prompt cannot be verified against the archived baseline digest."
    )


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
    manifest = _workspace_manifest(work)
    assert manifest == all_files
    all_file_digests = {
        name: suite.digest(content) for name, content in manifest.items()
    }
    assert all_file_digests == capture["recipient_after_sha256"], _delivery_key(capture)

    grade = _replay_probes(case, work)
    assert grade == capture["probe"], _delivery_key(capture)
    assert _workspace_manifest(work) == manifest
    return grade


def test_replays_captured_intake_deliveries(
    tmp_path: Path, baseline_inputs: _BaselineInputs
) -> None:
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

    instructions = baseline_inputs.instructions
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


def _sender_packet(
    case: IntakeCase,
    capture: _CapturedDelivery,
    local_session: Path,
    baseline: _BaselineInputs,
    hooks_by_path: dict[str, bytes],
) -> bytes:
    if capture["cohort"] == "full":
        assert "sender_session_path" not in capture
        return baseline.instructions
    if capture["cohort"] == "clipped":
        case = intake_probe.compact_case(case)
    original_session = PurePosixPath(capture["sender_session_path"])
    assert original_session.is_absolute() and original_session.name == protocol.SESSION
    _materialize(
        local_session,
        {
            **{f"hooks/{path}": source for path, source in hooks_by_path.items()},
            protocol.TRANSCRIPT: recall_driver._transcript_bytes(case["original"]),
        },
    )
    common = recall_driver._compact_context(local_session)
    delivered, clipped = recall_driver.context_for_arm(
        common, capture["arm"], original_session
    )
    assert clipped
    return b"\n\n".join((baseline.instructions, delivered, case["summary"].encode()))


def test_reconstructs_intake_sender_packets(
    tmp_path: Path, baseline_inputs: _BaselineInputs
) -> None:
    """Rebuild and hash the sender's delivered instructions for each trial."""
    hooks_by_path = baseline_inputs.hooks_by_path
    if hooks_by_path is None:
        pytest.skip(
            "The pinned recall hook is outside this shallow checkout and the "
            "checked-out hook dependencies cannot be verified against its manifest."
        )
    all_cases = intake_probe.read_cases()
    for each_index, each_capture in enumerate(_read_captures()):
        packet = _sender_packet(
            all_cases[each_capture["case"]],
            each_capture,
            tmp_path / str(each_index),
            baseline_inputs,
            hooks_by_path,
        )
        assert suite.digest(packet) == each_capture["sender_input_sha256"], (
            _delivery_key(each_capture)
        )
