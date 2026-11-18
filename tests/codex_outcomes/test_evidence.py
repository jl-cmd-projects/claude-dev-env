"""Exercise failures against the same replay and live writer used by the benchmark."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent


@pytest.mark.parametrize("invalid_receipt", [False, True])
def test_hosted_refuses_an_invalid_comparison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid_receipt: bool) -> None:
    monkeypatch.syspath_prepend(str(HERE))
    homes = [tmp_path / name for name in ("baseline", "candidate")]
    for home in homes:
        (home / ".codex").mkdir(parents=True)
        (home / ".codex/codex-sol.md").write_text("identical")
        expected = hashlib.sha256(b"identical").hexdigest()
        if invalid_receipt and home == homes[1]:
            expected = "wrong receipt"
        (home / "install.json").write_text(json.dumps({"prompt_sha256": expected}))
    with pytest.raises(ValueError, match="identical|installation receipt"):
        importlib.import_module("hosted").serve(*homes, tmp_path, tmp_path / "records", 1, HERE / "cases.json")
    assert not list(tmp_path.glob("order-*"))


def test_captured_file_violation_remains_reportable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(HERE))
    replay = importlib.import_module("replay_hosted")
    rows = [json.loads(line) for line in (HERE / "evidence/hosted.jsonl").read_text().splitlines()]
    rows[0].update(protected_changes=["ORDER.md"], violations=["changed protected input"])
    rows[0]["rating_input_sha256"] = replay.rating_input(rows[0])
    journal = tmp_path / "journal.jsonl"
    journal.write_text("\n".join(json.dumps(row) for row in rows))
    assert replay.replay(journal)["baseline"]["state"] == 13
    rows[0]["final_sha256"] = "changed reply"
    journal.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError, match="judgment and source"):
        replay.replay(journal)


def test_writer_needs_verified_application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(HERE))
    case = json.loads((HERE / "writer_case.json").read_text())[0]
    desk = importlib.import_module("receiver").Receiver(tmp_path, case)
    readback = {"operation": "status", "key": None, "value": None}
    assert desk.respond(readback)["writer"]["revision"] == 7
    assert not desk.score()["receipt_goal"]
    desk.respond({"operation": "deliver", "key": "alder-inbox", "value": "shelf 4: gold"})
    assert not desk.score()["receipt_goal"]
    assert desk.respond(readback)["writer"]["revision"] == 8
    assert desk.score()["receipt_goal"]
