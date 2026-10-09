"""Behavior tests for correction_filing with a stand-in gh on PATH."""

from __future__ import annotations

import importlib
import io
import json
import os
import stat
import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

correction_filing = importlib.import_module("correction_filing")

STAND_IN_GH = r'''#!/usr/bin/env python3
import json, os, sys
from urllib.parse import parse_qs, urlsplit
store = os.environ["STAND_IN_GH_STORE"]
issues = json.load(open(store)) if os.path.exists(store) else []
args = sys.argv[1:]
if "POST" in args:
    fields = dict(args[i + 1].split("=", 1) for i, a in enumerate(args) if a == "-f")
    number = len(issues) + 1
    url = "https://example.test/issues/%d" % number
    issues.append({"number": number, "title": fields["title"], "url": url,
                   "body": fields["body"], "label": fields["labels[]"], "state": "open"})
    json.dump(issues, open(store, "w"))
    print(url)
else:
    query = parse_qs(urlsplit(args[2]).query)
    state = query["state"][0]
    for i in issues:
        if i["label"] == query["labels"][0] and (state == "all" or i["state"] == state):
            print(json.dumps({k: i[k] for k in ("number", "title", "url", "body")}))
'''


@pytest.fixture
def filing_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    gh_path = bin_directory / "gh"
    gh_path.write_text(STAND_IN_GH, encoding="utf-8")
    gh_path.chmod(gh_path.stat().st_mode | stat.S_IEXEC)
    store_path = tmp_path / "issues.json"
    config_file = tmp_path / "correction-capture.json"
    config_file.write_text(json.dumps({"repository": "owner/name", "label": "correction"}))
    monkeypatch.setenv("PATH", str(bin_directory) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("STAND_IN_GH_STORE", str(store_path))
    monkeypatch.setenv("CLAUDE_CORRECTION_CAPTURE_PATH", str(config_file))
    return store_path


def _stored_issues(store_path: Path) -> list[dict[str, object]]:
    return json.loads(store_path.read_text()) if store_path.exists() else []


def test_should_file_one_labeled_issue_quoting_the_text(filing_environment: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert correction_filing.main(["file", "--text", "use shorter replies"]) == 0
    all_issues = _stored_issues(filing_environment)
    assert len(all_issues) == 1
    assert all_issues[0]["label"] == "correction"
    assert "> use shorter replies" in all_issues[0]["body"]
    assert "Filed: https://example.test/issues/1" in capsys.readouterr().out


def test_should_file_a_replayed_correction_once(filing_environment: Path, capsys: pytest.CaptureFixture[str]) -> None:
    correction_filing.main(["file", "--text", "stop  asking me"])
    assert correction_filing.main(["file", "--text", "stop asking me"]) == 0
    assert len(_stored_issues(filing_environment)) == 1
    assert "Already filed: https://example.test/issues/1" in capsys.readouterr().out


def test_should_dedupe_on_a_supplied_key(filing_environment: Path) -> None:
    correction_filing.main(["file", "--text", "first", "--dedupe-key", "msg-7"])
    correction_filing.main(["file", "--text", "second", "--dedupe-key", "msg-7"])
    correction_filing.main(["file", "--text", "second", "--dedupe-key", "msg-8"])
    assert len(_stored_issues(filing_environment)) == 2


def test_should_mask_tokens_and_emails(filing_environment: Path) -> None:
    correction_filing.main(
        ["file", "--text", "you leaked ghp_" + "a" * 36 + " and me@example.com"]
    )
    body = _stored_issues(filing_environment)[0]["body"]
    assert "ghp_" not in body and "me@example.com" not in body
    assert body.count("[redacted]") == 2


def test_should_file_nothing_without_config(filing_environment: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("CLAUDE_CORRECTION_CAPTURE_PATH", str(tmp_path / "absent.json"))
    assert correction_filing.main(["file", "--text", "anything"]) == 1
    assert _stored_issues(filing_environment) == []
    assert "No correction filing config" in capsys.readouterr().err


def test_should_file_nothing_for_empty_text(filing_environment: Path) -> None:
    assert correction_filing.main(["file", "--text", "   "]) == 1
    assert _stored_issues(filing_environment) == []


def test_should_list_open_corrections(filing_environment: Path, capsys: pytest.CaptureFixture[str]) -> None:
    correction_filing.main(["list"])
    assert "No open corrections." in capsys.readouterr().out
    correction_filing.main(["file", "--text", "use plain words"])
    capsys.readouterr()
    correction_filing.main(["list"])
    assert "#1 Correction: use plain words https://example.test/issues/1" in capsys.readouterr().out


def test_should_build_title_and_body_from_text() -> None:
    assert correction_filing.issue_title_for("a\nb") == "Correction: a b"
    body = correction_filing.issue_body_for("x\ny", "flag", "abcdef0123456789")
    assert "> x\n> y" in body and "Source: flag" in body
    assert "<!-- correction-dedupe: abcdef0123456789 -->" in body


def test_should_read_target_and_reject_incomplete_config(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"repository": "o/n", "label": "l"}))
    assert correction_filing.load_filing_target(good) == correction_filing.FilingTarget("o/n", "l")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"repository": "o/n"}))
    with pytest.raises(correction_filing.FilingConfigMissing):
        correction_filing.load_filing_target(bad)


def test_should_dedupe_from_the_ledger_when_the_listing_lags(filing_environment: Path, capsys: pytest.CaptureFixture[str]) -> None:
    correction_filing.main(["file", "--text", "keep replies short"])
    filing_environment.write_text("[]")
    capsys.readouterr()
    correction_filing.main(["file", "--text", "keep replies short"])
    assert "Already filed: https://example.test/issues/1" in capsys.readouterr().out


def test_should_read_the_text_from_stdin_without_expanding_it(filing_environment: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO('say "$(whoami)" and `id`\n'))
    assert correction_filing.main(["file"]) == 0
    assert '> say "$(whoami)" and `id`' in _stored_issues(filing_environment)[0]["body"]


def test_should_file_again_after_the_config_names_another_repository(filing_environment: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    correction_filing.main(["file", "--text", "keep replies short"])
    filing_environment.write_text("[]")
    (tmp_path / "correction-capture.json").write_text(json.dumps({"repository": "owner/other", "label": "correction"}))
    capsys.readouterr()
    correction_filing.main(["file", "--text", "keep replies short"])
    assert "Filed: https://example.test/issues/1" in capsys.readouterr().out
