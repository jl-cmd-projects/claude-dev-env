"""Blind fresh hosted replies, then join the reviewed packet to the receiving journals."""

import argparse
import hashlib
import json
import secrets
from pathlib import Path

from completion_eval.config import study
from completion_eval.errors import EvidenceRunFatal
from replay_hosted import contract_hash, rating_input


def collect(all_directories: list[Path], all_replies: dict[str, str]) -> tuple[dict, dict]:
    """Bind worker replies to the assignment and its receiver log.

    Args:
        all_directories: Controller record directories.
        all_replies: Private replies by work-order identifier.

    Returns:
        Blinded packets and matching evidence records.

    Raises:
        EvidenceRunFatal: A capture conflicts with its assignment.
    """
    packets = {}
    records = {}
    for each_directory in all_directories:
        for each_meta in json.loads((each_directory / "orders.json").read_text()):
            key = each_meta["work_id"]
            each_row = json.loads((each_directory / (key + study.JSON_EXTENSION)).read_text())
            if each_row["receiver_error"] or any(each_row[field] != each_meta[field] for field in each_meta):
                raise EvidenceRunFatal("Worker capture differs from its assignment or receiver failed")
            each_identity = each_row["blind_id"]
            if each_identity in records:
                raise EvidenceRunFatal("Repeated blinded assignment")
            records[each_identity] = {field: each_row[field] for field in (
                "arm", "case", "repeat", "blind_id", "prompt_sha256", "seconds", "status",
                "receipts", "protected_changes", "violations", "desk_events",
            )}
            closing = all_replies.get(key, "") if each_row["status"] == "timeout" else all_replies[key]
            contract = each_meta["contract"]
            if contract["id"] != each_row["case"]:
                raise EvidenceRunFatal("The staged contract names a different case")
            records[each_identity]["contract_sha256"] = contract_hash(contract)
            records[each_identity]["final_sha256"] = hashlib.sha256(closing.encode()).hexdigest()
            packets[each_identity] = {
                "id": each_identity, "contract": contract, "final": closing,
                "events": each_row["desk_events"], "changes": each_row["protected_changes"],
            }
    return packets, records


def main() -> None:
    """Write the blinded packet or the reviewed journal.

    Raises:
        EvidenceRunFatal: The review differs from the captured packet.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--replies", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--ratings", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    packets, records = collect(args.directories, json.loads(args.replies.read_text()))
    if args.ratings is None and args.evidence is None:
        shuffled = list(packets.values())
        secrets.SystemRandom().shuffle(shuffled)
        with args.packet.open("x") as packet_stream:
            json.dump(shuffled, packet_stream, indent=study.JSON_INDENT)
        return
    if not args.ratings or not args.evidence:
        parser.error("Provide both --ratings and --evidence after blinded review")
    judged = json.loads(args.packet.read_text())
    ratings = json.loads(args.ratings.read_text())
    if len(judged) != len(packets) or {each_row["id"]: each_row for each_row in judged} != packets or set(ratings) != set(packets):
        raise EvidenceRunFatal("Judged packet differs from the source replies or receiving journals")
    for each_identity, each_row in records.items():
        each_row["rating"] = {field: ratings[each_identity][field] for field in (*study.ALL_DIMENSIONS, "evidence")}
        each_row["rating_input_sha256"] = rating_input(each_row)
    with args.evidence.open("x") as receipt_stream:
        for each_row in records.values():
            receipt_stream.write(json.dumps(each_row, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
