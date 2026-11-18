"""Serve a publication approval update and an independent snapshot release."""

import sys
from copy import deepcopy
from http import HTTPStatus
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


core_directory = Path(__file__).resolve().parents[1]
core_import_path = str(core_directory)
if core_import_path not in sys.path:
    sys.path.insert(0, core_import_path)
core_spec = spec_from_file_location("environment_blocker_service", core_directory / "service.py")
if core_spec is None or core_spec.loader is None:
    raise ImportError("Cannot load Launch Ledger fixture service")
core_service = module_from_spec(core_spec)
core_spec.loader.exec_module(core_service)


class ContinuationFixture(core_service.Fixture):
    def __init__(self, case: core_service.FixtureCase, run_dir: Path) -> None:
        super().__init__(case, run_dir)
        self.state["approval_status"] = None
        self.save_state()

    def object_request(
        self, operation: str, target: str, if_match: str | None = None, body: object = None
    ) -> core_service.HttpReply:
        """Keep the next scheduled snapshot unavailable until the desk update.

        Args:
            operation: Read, capability, or write action.
            target: Requested record name.
            if_match: Current ETag supplied by a write request.
            body: Decoded JSON supplied by a write request.

        Returns:
            The HTTP status, JSON payload, and headers for the action.
        """
        snapshot = self.case["continuation"]["snapshot"]
        if operation == "read" and target == snapshot and self.state["approval_status"] is None:
            return self.failure(operation, target, HTTPStatus.TOO_EARLY, "Review Desk snapshot is pending its scheduled update")
        return super().object_request(operation, target, if_match, body)

    def operator_input(self) -> None:
        """Read the private one-shot desk decision from the operator's stdin."""
        for each_line in sys.stdin:
            status = each_line.strip()
            if status in {"active", "pending"}:
                self._publish_desk_update(status)

    def _publish_desk_update(self, status: str) -> None:
        expected = self.case["expected"]
        publication = expected["target"]
        continuation = self.case["continuation"]
        snapshot = continuation["snapshot"]
        with self.lock:
            if self.state["approval_status"] is not None:
                return
            if not any(receipt["recipient"] == expected["recipient"] for receipt in self.state["messages"]):
                return
            snapshot_content = deepcopy(continuation["released_snapshot"])
            snapshot_version = self.state["objects"][snapshot]["version"] + 1
            self.state["objects"][snapshot] = {"value": snapshot_content, "version": snapshot_version}
            self.state["approval_status"] = status
            if status == "active":
                self.state["grants"].append(publication)
            self.save_state()
            self.record(
                "operator_status", publication, HTTPStatus.OK,
                approval_status=status, snapshot_target=snapshot,
                snapshot_value=snapshot_content, snapshot_version=snapshot_version,
            )


if __name__ == "__main__":
    core_service.main(sys.stdout, Path(__file__).with_name("cases.json"), ContinuationFixture)
