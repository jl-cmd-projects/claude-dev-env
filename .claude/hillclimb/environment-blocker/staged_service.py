import sys
from http import HTTPStatus
from pathlib import Path

import service


class StagedFixture(service.Fixture):
    def __init__(self, case: service.FixtureCase, run_dir: Path) -> None:
        super().__init__(case, run_dir)
        self.stage = case["stage"]
        self.visible_keys = set()
        self.has_observed_denial = False

    def object_request(
        self, operation: str, target: str, if_match: str | None = None, body: object = None
    ) -> service.HttpReply:
        """Expose the first denial and catalog link in one manifest response.

        Args:
            operation: Read, capability, or write action.
            target: Requested manifest, catalog key, or publication record.
            if_match: Current ETag supplied by a write request.
            body: Decoded JSON supplied by a write request.

        Returns:
            The HTTP status, JSON payload, and headers from the staged action.
        """
        if operation == "read" and target in self.stage["sources"] and target not in self.visible_keys:
            return self.failure(operation, target, 404, "Catalog key has not been resolved")
        status, record, headers = super().object_request(operation, target, if_match, body)
        publication = self.stage["publication"]
        decision = self.case["restrictions"][publication]
        if operation in {"capability", "write"} and target == publication and status == decision["status"]:
            self.has_observed_denial = True
        if operation != "read" or status != HTTPStatus.OK:
            return status, record, headers
        if target == self.stage["manifest"]:
            self.visible_keys.add(record["value"]["first_key"])
            record["publication"] = {"target": publication, "owner": self.stage["owner"], **decision}
            if not self.has_observed_denial:
                self.record("capability", publication, via=target, **decision)
                self.has_observed_denial = True
        elif target in self.stage["sources"] and "next_key" in record["value"]:
            self.visible_keys.add(record["value"]["next_key"])
        return status, record, headers


if __name__ == "__main__":
    service.main(sys.stdout, Path(__file__).with_name("staged_case.json"), StagedFixture)
