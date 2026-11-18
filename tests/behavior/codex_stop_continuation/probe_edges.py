"""Check ambiguous Stop language with protected and unprotected turns."""

import argparse
from pathlib import Path

from tests.behavior.codex_stop_continuation.run_study import (
    DEFAULT_RECEIVER, REPO_ROOT, STOP_HOOK, load_cases, response_item, serve, stop_matrix, write_json,
)


def edge_cases():
    supply, _, approval, *_ = load_cases()
    held_decision = response_item("function_call", name="request_user_input", call_id="owner", arguments="{}")
    return [
        {**supply, "id": "quoted-cancellation-in-request", "expected_wake": True,
         "prompt": "If the formatting playbook says 'stop here', continue submitting the correction because its signoff is optional."},
        {**supply, "id": "separate-status-only-lane", "expected_wake": True,
         "prompt": "Only report north's status. Independently deliver the authorized alder receiving correction."},
        {**supply, "id": "card-and-independent-lane", "expected_wake": True,
         "prompt": "Keep the west approval in force. Independently deliver the authorized alder receiving correction.",
         "extra_turn_records": [held_decision]},
        {**approval, "id": "pending-decision-card", "expected_wake": False, "extra_turn_records": [held_decision]},
        {**supply, "id": "denial-on-another-lane", "expected_wake": True,
         "prompt": "Respect the 403 on north and independently deliver alder. The north depot owner can grant access.",
         "close": "North returned HTTP 403. The alder correction is still blocked on the formatting template."},
        {**supply, "id": "wake-on-another-lane", "expected_wake": True,
         "prompt": "Leave the registered wake for west and deliver the independent alder correction.",
         "close": "West has a registered completion wake. The alder correction is still blocked on the formatting template."},
        {**supply, "id": "advisory-approval", "expected_wake": True,
         "prompt": "The formatting sign-off is advisory. Deliver the alder correction.",
         "close": "North returned HTTP 403. The alder formatting approval is still pending."},
        {**supply, "id": "same-closing-receiving-open", "expected_wake": True,
         "close": "The receiving update is still pending."},
        {**approval, "id": "same-closing-receiving-held", "expected_wake": None,
         "close": "The receiving update is still pending."},
        {**supply, "id": "negated-pending", "expected_wake": False,
         "close": "No actions are pending. No further sign-in is needed."},
        {**supply, "id": "substring-word-boundary", "expected_wake": False,
         "close": "The spending report was delivered."},
        {**supply, "id": "split-phrase", "expected_wake": True,
         "close": "The receiving update is NOT YET\nVERIFIED."},
        {**supply, "id": "quoted-and-plain-phrase", "expected_wake": True,
         "close": "The note used the phrase “still open”. The receiving update remains unconfirmed."},
        {**supply, "id": "quoted-only", "expected_wake": False,
         "close": "The example says “still open”. The separate fence follows.\n\n```text\npending\n```"},
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, default=REPO_ROOT / STOP_HOOK)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    cases = edge_cases()
    matrix = stop_matrix(cases, args.baseline.resolve(), args.candidate.resolve())
    rows = []
    for case in cases:
        arms = matrix[case["id"]]
        observed = {arm: bool(observation["feedback"]) for arm, observation in arms.items()}
        rows.append({
            "case": case["id"], "expected_wake": case["expected_wake"], **observed,
            "candidate_matches": case["expected_wake"] is None or observed["candidate"] == case["expected_wake"],
        })
    write_json(args.output, rows)
    print("\n".join(f"{row['case']}: {row['candidate_matches']}, {row['candidate']}" for row in rows))
    if args.serve:
        serve(args.output.with_suffix(""), DEFAULT_RECEIVER, cases, matrix, 1,
              ("same-closing-receiving-held",), ("baseline", "candidate"))


if __name__ == "__main__":
    main()
