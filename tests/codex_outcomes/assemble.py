"""Blind fresh hosted replies, then join the reviewed packet to the receiving journals."""

import argparse
import hashlib
import json
import secrets
from pathlib import Path

from replay_hosted import DIMENSIONS, HERE, rating_input


def collect(directories, replies):
    cases = {case["id"]: case for path in ("cases.json", "writer_case.json")
             for case in json.loads((HERE / path).read_text())}
    packets = {}
    records = {}
    for directory in directories:
        for meta in json.loads((directory / "orders.json").read_text()):
            key = meta["work_id"]
            row = json.loads((directory / (key + ".json")).read_text())
            if row["receiver_error"] or any(row[field] != meta[field] for field in meta):
                raise ValueError("Worker capture differs from its assignment or receiver failed")
            identity = row["blind_id"]
            if identity in records:
                raise ValueError("Repeated blinded assignment")
            records[identity] = {field: row[field] for field in (
                "arm", "case", "repeat", "blind_id", "prompt_sha256", "seconds", "status",
                "receipts", "protected_changes", "violations", "desk_events",
            )}
            closing = replies.get(key, "") if row["status"] == "timeout" else replies[key]
            records[identity]["final_sha256"] = hashlib.sha256(closing.encode()).hexdigest()
            packets[identity] = {
                "id": identity, "contract": cases[row["case"]], "final": closing,
                "events": row["desk_events"], "changes": row["protected_changes"],
            }
    return packets, records


def main():
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
            json.dump(shuffled, packet_stream, indent=2)
        return
    if not args.ratings or not args.evidence:
        parser.error("Provide both --ratings and --evidence after blinded review")
    judged = json.loads(args.packet.read_text())
    ratings = json.loads(args.ratings.read_text())
    if len(judged) != len(packets) or {row["id"]: row for row in judged} != packets or set(ratings) != set(packets):
        raise ValueError("Judged packet differs from the source replies or receiving journals")
    for identity, row in records.items():
        row["rating"] = {field: ratings[identity][field] for field in (*DIMENSIONS, "evidence")}
        row["rating_input_sha256"] = rating_input(row)
    with args.evidence.open("x") as receipt_stream:
        for row in records.values():
            receipt_stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
