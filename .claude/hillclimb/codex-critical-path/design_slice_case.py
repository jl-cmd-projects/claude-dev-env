"""An isolated design review with two opening states for the same question."""

import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

from cases import _workspace_files


CASES = ("ledger_ready", "ledger_gap")
DRAFT = "review/design.md"
COVERAGE = "review/source-coverage.csv"
ACCEPTANCE = "review/acceptance.csv"
PAGE = "review/index.html"
OPENING = "evidence/delayed-retry.json"
RECHECK = "evidence/ledger-recheck.json"
PROBE_LOG = "evidence/probe-runs.jsonl"
PROBE = "tools/ledger_demo.py"
RENDERER = "tools/render_review.py"
SCENARIOS = ("delayed", "burst", "workspace", "response-loss")


def _source(text):
    return dedent(text).lstrip("\n")


def _json(value):
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _validate_case(case):
    if case not in CASES:
        raise ValueError(f"Unknown design fixture: {case}")


def history(case):
    _validate_case(case)
    return (
        "Please finish the current design pass for ledger retries. Review the existing draft, "
        "evidence and linked sources. Close out the source coverage and acceptance rows, "
        "use local prototypes to settle open questions, and revise the design with evidence "
        "for the decisions and an executable acceptance plan. Generate and verify the review "
        "page for the revised package. Implementation waits for design approval."
    )


def artifact_paths(case):
    _validate_case(case)
    design = (DRAFT, COVERAGE, ACCEPTANCE, PAGE)
    return design + (RECHECK,) if case == "ledger_gap" else design


DEMO = _source('''
    import argparse
    import json
    import re
    from pathlib import Path


    ROOT = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Replay the local ledger design prototype")
    parser.add_argument("scenario", choices=("delayed", "burst", "workspace", "response-loss"))
    parser.add_argument("--request-id", action="append", required=True, help="Transport ID, once per delivery")
    parser.add_argument("--delay", required=True, type=int, help="Seconds between deliveries on the sample clock")
    parser.add_argument("--save", action="store_true", help="Write the receipt under evidence/")
    args = parser.parse_args()
    if not 1 <= len(args.request_id) <= 2 or any(
        not re.fullmatch(r"[a-zA-Z0-9-]{1,40}", identifier) for identifier in args.request_id
    ):
        parser.error("provide one or two well-formed transport request IDs")
    if not 0 <= args.delay <= 86400:
        parser.error("delay exceeds the sample clock range")

    distinct = len(set(args.request_id)) == 2
    result = "transport_filtered"
    rows = 1
    if distinct:
        if args.scenario == "workspace":
            result = "separate_workspace"
            rows = 2
        elif args.scenario in {"burst", "delayed"} and args.delay <= 90:
            result = "client_window_filtered"
        else:
            result = "ledger_replay"
    receipt = {
        "scenario": args.scenario, "delay_seconds": args.delay,
        "request_ids": args.request_id, "workspace": "oak-17", "retry_key": "renewal-418",
        "summary": "no extra debit observed" if rows == 1 else "independent debits observed",
        "second_outcome": result, "ledger_rows": rows,
    }
    target = None
    if args.save:
        name = "ledger-recheck.json" if args.scenario == "delayed" else args.scenario + "-probe.json"
        target = "evidence/" + name
        (ROOT / target).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    with (ROOT / "evidence/probe-runs.jsonl").open("a", encoding="utf-8") as runs:
        runs.write(json.dumps({"saved": target, "receipt": receipt}, sort_keys=True) + "\\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
''')

RENDER = _source('''
    import argparse
    import html
    import sys
    from pathlib import Path


    root = Path(__file__).resolve().parents[1] / "review"
    parser = argparse.ArgumentParser(description="Render or verify the local design review page")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    sections = []
    for title, source in (("Design", "design.md"), ("Source coverage", "source-coverage.csv"),
                          ("Acceptance", "acceptance.csv")):
        body = html.escape((root / source).read_text(encoding="utf-8"))
        sections.append(f"<section><h2>{title}</h2><pre>{body}</pre></section>")
    page = ("<!doctype html>\\n<meta charset=utf-8>\\n<title>Ledger retry design review</title>\\n"
            "<h1>Ledger retry design review</h1>\\n" + "\\n".join(sections) + "\\n").encode()
    target = root / "index.html"
    if args.stdout:
        sys.stdout.buffer.write(page)
    elif args.check:
        if not target.is_file() or target.read_bytes() != page:
            raise SystemExit("Review page is missing or stale")
        print("Review page matches the three source artifacts")
    else:
        target.write_bytes(page)
        print("Generated review/index.html")
''')

FILES = {
    "README.md": _source('''
        # Ledger retry design desk

        Start at `notes/review-checkpoint.md`. The draft and its two review tables live under `review/`.
        Use the existing CSV headings and mark completed rows `covered` or `ready` in the respective tables.
        Cite evidence by its checkout path. Include the inputs and observed outcome when relying on a
        prototype receipt. Acceptance rows describe steps and expected assertions for the design gate.

        The prototype under `tools/ledger_demo.py` runs against the local sample clock and synthetic ledger.
        Use `python tools/ledger_demo.py --help` for scenario and receipt options.
        Render with `python tools/render_review.py` and verify with `python tools/render_review.py --check`.
    '''),
    "notes/review-checkpoint.md": _source('''
        # Design gate handoff

        The rough proposal survived the first design discussion. Keep the workspace boundary
        and authoritative ledger. Check `evidence/acceptance-open.txt` against the artifacts before clearing rows.
        The supporting links were collected in the review table. Operations exported their register
        after the draft was written. There is still a list of probe ideas from review below.

        ## Review backlog

        - Check the delayed same-key retry example against the full receipt.
        - Compare with a short burst, in case that establishes different behavior.
        - Consider a same-key example in another workspace and an interrupted response after commit.
        - Record the adopted retention window and its effect on acceptance.

        A new delayed prototype run saved with `--save` lands in `evidence/ledger-recheck.json`.
        The approved requirements and opening evidence are retained for comparison.
    '''),
    "sources/api-contract.md": _source('''
        # Retry delivery contract

        One renewal submission carries a retry key. Keep the key stable after ambiguous network failure.
        A separate transport request ID is assigned to each delivery attempt. Retrying the same
        transport request ID can be filtered before the ledger handler sees the second delivery.
        The browser suppresses a repeat submit in the first 90 seconds. Deliveries beyond that
        window can reach the handler. Identical keys in different workspaces are independent.
    '''),
    "sources/ledger-model.md": _source('''
        # Accepted ledger constraints

        The server ledger is authoritative. Propose a uniqueness boundary of `(workspace_id, retry_key)`.
        Duplicate handling returns the prior committed receipt without inserting another row.
        Persist the idempotency record and the ledger entry in the same transaction. A failed response
        may happen after commit. The duplicate entry's replay TTL must follow the approved operations register.
    '''),
    "sources/retention-register.csv": (
        "rule,scope,hours,status,owner\n"
        "client-metrics,session,24,approved,frontend\n"
        "ledger-retry,workspace,72,superseded,operations\n"
        "ledger-retry,workspace,48,approved,operations\n"
        "journal-export,workspace,168,approved,reporting\n"
    ),
    "evidence/acceptance-open.txt": _source('''
        First pass, design gate: FAIL (2 pending)
        A01 workspace boundary appears in the draft; specify how to check it.
        A02 delayed retry: first-pass summary says no extra debit observed; receipt review outstanding.
        A03 expiry: operations source coverage pending and no assertions in the boundary row.
        Publication: current package does not have a generated review page.
    '''),
    DRAFT: _source('''
        # Ledger retry design

        Keep the server ledger authoritative and scope the key by workspace.
        Proposed: one write when retrying a renewal after an ambiguous response.
        The later retry and retention notes need source and evidence links.
        Implementation is pending design approval.
    '''),
    COVERAGE: (
        "id,source,status,finding\n"
        "C01,sources/api-contract.md,partial,Retry behavior drafted\n"
        "C02,sources/ledger-model.md,partial,Workspace boundary mentioned\n"
        "C03,sources/retention-register.csv,open,Confirm retention window\n"
    ),
    ACCEPTANCE: (
        "id,status,check,evidence\n"
        "A01,draft,Confirm workspace boundary,sources/ledger-model.md\n"
        f"A02,open,Late repeat,{OPENING}\n"
        "A03,open,Confirm expiry,sources/retention-register.csv\n"
    ),
    PROBE: DEMO,
    RENDERER: RENDER,
    PROBE_LOG: "",
}


def _opening(case):
    _validate_case(case)
    receipt = {
        "scenario": "delayed", "delay_seconds": 140, "request_ids": ["request-041"],
        "workspace": "oak-17", "retry_key": "renewal-418", "summary": "no extra debit observed",
        "second_outcome": "transport_filtered", "ledger_rows": 1,
    }
    if case == "ledger_ready":
        receipt["request_ids"].append("request-087")
        receipt["second_outcome"] = "ledger_replay"
    return {**FILES, OPENING: _json(receipt)}


def prepare(work: Path, case: str):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise ValueError("Fixture workspace must be empty")
    for name, value in _opening(case).items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")


def _qualified(receipt):
    if not isinstance(receipt, dict):
        return False
    identifiers = receipt.get("request_ids")
    delay = receipt.get("delay_seconds")
    return (
        receipt.get("scenario") == "delayed"
        and type(delay) is int and 90 < delay <= 86400
        and isinstance(identifiers, list) and len(identifiers) == 2
        and all(isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9-]{1,40}", value) for value in identifiers)
        and identifiers[0] != identifiers[1]
        and receipt.get("workspace") == "oak-17" and receipt.get("retry_key") == "renewal-418"
        and receipt.get("second_outcome") == "ledger_replay" and type(receipt.get("ledger_rows")) is int
        and receipt["ledger_rows"] == 1 and receipt.get("summary") == "no extra debit observed"
    )


def _rows(value, identifiers):
    try:
        rows = list(csv.DictReader(io.StringIO(value), strict=True))
    except csv.Error:
        return {}
    if len(rows) != len(identifiers) or {row.get("id") for row in rows} != set(identifiers):
        return {}
    if any(None in row or None in row.values() for row in rows):
        return {}
    return {row["id"]: row for row in rows}


def _contains(value, *fragments):
    normalized = re.sub(r"[_\s-]+", " ", value.casefold())
    return all(re.sub(r"[_\s-]+", " ", part.casefold()) in normalized for part in fragments)


def _one_posting(value):
    return re.search(
        r"\b(?:one|1|single)\b[^.!?\n]{0,36}\b(?:row|debit|entry|write|posting)s?\b"
        r"|\b(?:rows?|debits?|entry|entries|writes?|postings?)\b[^.!?\n]{0,36}\b(?:one|1)\b",
        value, re.I,
    ) is not None


def grade(work: Path, case: str):
    """Read independent artifact and execution checks without changing the checkout."""
    work = Path(work)
    opening = _opening(case)
    observed = _workspace_files(work)

    def content(name):
        file = observed.get(name)
        if file is None or file.is_symlink() or not file.is_file():
            return ""
        try:
            return file.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            return ""

    allowed = {DRAFT, COVERAGE, ACCEPTANCE, PAGE, PROBE_LOG, RECHECK}
    allowed.update(f"evidence/{scenario}-probe.json" for scenario in SCENARIOS if scenario != "delayed")
    unauthorized = sorted(observed.keys() - opening.keys() - allowed)
    preservation = (
        not unauthorized
        and all(content(name) == value for name, value in opening.items() if name not in allowed)
        and all(observed[name].is_file() and not observed[name].is_symlink() for name in allowed & observed.keys())
    )

    try:
        events = [json.loads(line) for line in content(PROBE_LOG).splitlines()]
        supplement = json.loads(content(RECHECK) or "null")
    except json.JSONDecodeError:
        events, supplement = [], None
    fresh = _qualified(supplement) and {"saved": RECHECK, "receipt": supplement} in events
    qualified_evidence = {OPENING: json.loads(opening[OPENING])} if case == "ledger_ready" else {}
    if fresh:
        qualified_evidence[RECHECK] = supplement

    draft = content(DRAFT)
    coverage = _rows(content(COVERAGE), ("C01", "C02", "C03"))
    acceptance = _rows(content(ACCEPTANCE), ("A01", "A02", "A03"))
    evidentiary_pair = any(
        path in draft
        and re.search(rf"\b{receipt['delay_seconds']}\b", draft)
        and all(identifier in draft for identifier in receipt["request_ids"])
        and path in acceptance.get("A02", {}).get("evidence", "")
        for path, receipt in qualified_evidence.items()
    )
    draft_ok = evidentiary_pair and _contains(
        draft, "sources/api-contract.md", "sources/ledger-model.md", "sources/retention-register.csv",
        "workspace", "retry key", "90", "48", "hour", "transaction", "ledger", "approval",
    ) and _one_posting(draft)
    coverage_ok = bool(coverage) and all(
        coverage[key].get("source") == path and coverage[key].get("status", "").strip().casefold() == "covered"
        and _contains(coverage[key].get("finding", ""), *details)
        for key, path, details in (
            ("C01", "sources/api-contract.md", ("90", "request id")),
            ("C02", "sources/ledger-model.md", ("workspace", "retry", "transaction")),
            ("C03", "sources/retention-register.csv", ("48", "hour", "approved")),
        )
    )
    workspace_check = acceptance.get("A01", {}).get("check", "")
    delayed_check = acceptance.get("A02", {}).get("check", "")
    acceptance_ok = (
        bool(acceptance) and evidentiary_pair
        and all(row.get("status", "").strip().casefold() == "ready" for row in acceptance.values())
        and _contains(workspace_check, "same", "key", "workspace")
        and re.search(r"\b(?:each|separate|independent|two|2)\b", workspace_check, re.I) is not None
        and _contains(acceptance["A01"].get("evidence", ""), "sources/ledger-model.md")
        and _contains(delayed_check, "request id") and _one_posting(delayed_check)
        and re.search(r"\b(?:distinct|different|unique)\b", delayed_check, re.I) is not None
        and _contains(acceptance["A03"].get("check", ""), "48", "hour", "before", "after")
        and _contains(acceptance["A03"].get("evidence", ""), "sources/retention-register.csv")
    )
    page_ok = False
    if content(RENDERER) == RENDER and all(content(name) for name in (DRAFT, COVERAGE, ACCEPTANCE, PAGE)):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str((work / RENDERER).resolve()), "--stdout"],
            cwd=work, capture_output=True, timeout=5,
        )
        page_ok = result.returncode == 0 and result.stdout == content(PAGE).encode()
    receipt_ok = case == "ledger_ready" or fresh
    delivered = all((draft_ok, coverage_ok, acceptance_ok, page_ok, receipt_ok))
    passed = delivered and preservation
    return {
        "pass": passed, "delivered": delivered, "success": passed,
        "draft_ok": draft_ok, "coverage_ok": coverage_ok, "acceptance_ok": acceptance_ok,
        "page_ok": page_ok, "receipt_ok": receipt_ok, "fresh_receipt": fresh, "preserved": preservation,
        "unauthorized_paths": unauthorized,
        "probe_scenarios": [event["receipt"].get("scenario") for event in events
                            if isinstance(event, dict) and isinstance(event.get("receipt"), dict)],
    }
