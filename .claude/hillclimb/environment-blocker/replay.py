"""Score every recorded session with its receipt-bound blind review."""

import json
from pathlib import Path

from grade import grade


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"


def replay():
    cases = {
        case["id"]: case
        for name in ("cases.json", "validation_cases.json", "staged_case.json")
        for case in json.loads((HERE / name).read_text())["cases"]
    }
    reviews = {
        item["message_sha256"]: item
        for item in json.loads((EVIDENCE / "semantic-review.json").read_text())
    }
    orders = json.loads((EVIDENCE / "launch.json").read_text())["work_orders"]
    missing = {(order, arm) for order, spec in orders.items() for arm in spec["worker_by_arm"]}
    for filename in ("pilot.jsonl", "validation.jsonl", "staged.jsonl"):
        for line in (EVIDENCE / filename).read_text().splitlines():
            record = json.loads(line)
            assignment = (record.get("repeat", record["case"]), record["arm"])
            if assignment not in missing:
                raise ValueError(f"Unknown or duplicate assignment: {assignment}")
            missing.remove(assignment)
            case = cases[record["case"]]
            args = (case, record["events"], record["state"])
            inventory = grade(*args)
            if inventory["status"] == "invalid_evidence":
                raise ValueError(f"Invalid evidence for {assignment}: {inventory}")
            deliveries = inventory["notifications"] + inventory["completion_update_candidates"]
            selected = [reviews[entry["message_sha256"]] for entry in deliveries]
            result = grade(*args, {"reviews": selected})
            if "stage" in case:
                first_contact = result["metrics"]["first_actionable_notification_seq"]
                result["metrics"]["catalog_reads_before_contact"] = sum(
                    event["operation"] == "read"
                    and event["target"] in case["stage"]["sources"]
                    and (first_contact is None or event["seq"] < first_contact)
                    for event in record["events"]
                )
            yield {"arm": record["arm"], "repeat": record.get("repeat", 1), **result}
    if missing:
        raise ValueError(f"Missing assignments: {sorted(missing)}")


if __name__ == "__main__":
    for result in replay():
        print(json.dumps(result, sort_keys=True))
