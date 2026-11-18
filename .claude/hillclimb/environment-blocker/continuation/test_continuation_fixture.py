"""Exercise the desk state transitions over the fixture's HTTP interface."""

import json
import subprocess
import sys
import unittest
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class ContinuationFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.run_dir = Path(directory.name) / "run"
        self.service_path = Path(__file__).with_name("service.py")
        self.case = json.loads(self.service_path.with_name("cases.json").read_text())["cases"][0]

    def test_active_update_releases_snapshot_and_grants_publication(self) -> None:
        self._exercise_decision("active", "pending", 200, "window-c")

    def test_pending_update_releases_snapshot_while_publication_remains_denied(self) -> None:
        self._exercise_decision("pending", "active", 428, "window-b")

    def _exercise_decision(self, decision: str, later_decision: str, expected_status: int, expected_saved: str) -> None:
        launch_command = [sys.executable, str(self.service_path), "serve", "--case", self.case["id"], "--run-dir", str(self.run_dir)]
        with subprocess.Popen(launch_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as server:
            try:
                port_file = self.run_dir / "port"
                self._wait_until(port_file.exists)
                self.endpoint = f"http://127.0.0.1:{port_file.read_text().strip()}"
                self._assert_pre_update()
                server.stdin.write(f"{decision}\n{later_decision}\n".encode())
                server.stdin.flush()
                self._wait_until(lambda: any(event["operation"] == "operator_status" for event in self._events()))
                self._assert_status_and_audit(decision, expected_status, expected_saved)
            finally:
                server.terminate()

    def _assert_pre_update(self) -> None:
        expected = self.case["expected"]
        snapshot = expected["audit"]["source"]
        self.assertEqual(self._http(f"capabilities/{expected['target']}")[0], 428)
        status, snapshot_reply, _ = self._http(f"objects/{snapshot}")
        self.assertEqual(status, 425)
        self.assertEqual(snapshot_reply["error"], "Review Desk snapshot is pending its scheduled update")
        self.assertEqual(self._http("operator-status", "POST", {"approval_status": "active"})[0], 404)
        self.assertIsNone(self._state()["approval_status"])
        note = {"recipient": expected["recipient"], "body": "Please ask Review Desk to approve publishing cedar-cutover-window."}
        self.assertEqual(self._http("messages", "POST", note)[0], 201)

    def _assert_status_and_audit(self, decision: str, expected_status: int, expected_saved: str) -> None:
        expected = self.case["expected"]
        snapshot_path = f"objects/{expected['audit']['source']}"
        primary_path = f"objects/{expected['target']}"
        audit_path = f"objects/{expected['audit']['target']}"
        status, snapshot, _ = self._http(snapshot_path)
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["value"], self.case["continuation"]["released_snapshot"])
        counts = {f"{label}_count": list(snapshot["value"].values()).count(label) for label in ("active", "held")}
        self.assertEqual(counts, expected["audit"]["value"])
        audit_etag = self._http(audit_path)[2]
        self.assertEqual(self._http(audit_path, "PUT", {"value": counts}, audit_etag)[0], 200)
        self.assertEqual(self._http(audit_path)[1]["value"], counts)
        primary_etag = self._http(primary_path)[2]
        self.assertEqual(self._http(primary_path, "PUT", {"value": expected["value"]}, primary_etag)[0], expected_status)
        self.assertEqual(self._http(primary_path)[1]["value"], expected_saved)
        self.assertEqual(self._http(f"capabilities/{expected['audit']['source']}")[0], 405)
        status_events = [event for event in self._events() if event["operation"] == "operator_status"]
        self.assertEqual(len(status_events), 1)
        self.assertEqual(status_events[0]["approval_status"], decision)
        self.assertEqual(status_events[0]["snapshot_version"], snapshot["version"])
        self.assertEqual(status_events[0]["snapshot_value"], snapshot["value"])
        self.assertEqual(self._state()["approval_status"], decision)
        expected_grants = [expected["target"]] if decision == "active" else []
        self.assertEqual(self._state()["grants"], expected_grants)

    def _state(self) -> dict[str, object]:
        return json.loads((self.run_dir / "state.json").read_text())

    def _events(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in (self.run_dir / "events.jsonl").read_text().splitlines()]

    def _wait_until(self, condition: Callable[[], bool]) -> None:
        deadline = monotonic() + 5
        while not condition():
            if monotonic() >= deadline:
                self.fail("Timed out waiting for a fixture receipt")
            sleep(0.01)

    def _http(
        self, route: str, method: str = "GET", body: object = None, etag: str | None = None
    ) -> tuple[int, dict[str, object], str | None]:
        headers = {"Content-Type": "application/json"}
        if etag:
            headers["If-Match"] = etag
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(f"{self.endpoint}/v1/{route}", method=method, data=payload, headers=headers)
        try:
            with urlopen(request, timeout=5) as reply:
                return reply.status, json.load(reply), reply.headers.get("ETag")
        except HTTPError as error:
            with error:
                return error.code, json.load(error), error.headers.get("ETag")


if __name__ == "__main__":
    unittest.main()
