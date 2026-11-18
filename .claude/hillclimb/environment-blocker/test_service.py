import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from service import Fixture, load_cases, render_prompt


CASES = load_cases()


class FixtureTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.run_dir = Path(temporary.name) / "run"

    def checkpoint(self):
        return json.loads((self.run_dir / "state.json").read_text(encoding="utf-8"))

    def events(self):
        lines = (self.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def test_safe_capability_lookup_matches_denial_without_mutation(self):
        case = CASES["denied-with-audit"]
        target = case["expected"]["target"]
        fixture = Fixture(case, self.run_dir)
        self.assertEqual(fixture.object_request("read", target)[0], 200)
        status, detail, _ = fixture.object_request("capability", target)
        self.assertEqual((status, detail["error"]), (403, case["expected"]["blocker"]["error"]))
        self.assertEqual(fixture.object_request("write", target, '"9"', {"value": "route-policy-7"})[0], 403)
        self.assertEqual(self.checkpoint()["objects"], case["objects"])
        self.assertEqual([event["operation"] for event in self.events()], ["read", "capability", "write"])

    def test_denial_does_not_affect_independent_audit(self):
        case = CASES["denied-with-audit"]
        audit = case["expected"]["audit"]
        fixture = Fixture(case, self.run_dir)
        self.assertEqual(fixture.object_request("capability", "eu-node-inventory")[0], 405)
        ok, _, headers = fixture.object_request("read", audit["target"])
        self.assertEqual(ok, 200)
        self.assertEqual(fixture.object_request("write", audit["target"], headers["ETag"], {"value": audit["value"]})[0], 200)
        self.assertEqual(self.checkpoint()["objects"][audit["target"]], {"value": audit["value"], "version": 2})
        self.assertEqual(self.events()[-1]["result_version"], 2)

    def test_stale_alias_read_succeeds_and_failed_write_identifies_canonical_record(self):
        case = CASES["stale-alias"]
        alias, target = next(iter(case["aliases"].items()))
        fixture = Fixture(case, self.run_dir)
        status, _, headers = fixture.object_request("read", alias)
        self.assertEqual(status, 200)
        status, detail, _ = fixture.object_request("write", alias, headers["ETag"], {"value": "canary-25"})
        self.assertEqual((status, detail["replacement"]), (409, target))
        self.assertEqual(self.checkpoint()["objects"], case["objects"])
        self.assertEqual([event["target"] for event in self.events()], [alias, alias])

    def test_version_precondition_keeps_conflicting_write_out_of_state(self):
        case = CASES["supported-publish"]
        target = case["expected"]["target"]
        fixture = Fixture(case, self.run_dir)
        self.assertEqual(fixture.object_request("write", target, '"6"', {"value": "train-42"})[0], 412)
        self.assertEqual(self.checkpoint()["objects"], case["objects"])

    def test_prompt_keeps_holdout_labels_and_grading_out_of_agent_context(self):
        case = CASES["absent-connector"]
        prompt = render_prompt(case, "http://127.0.0.1:27601")
        self.assertIn(case["prompt"], prompt)
        self.assertIn("http://127.0.0.1:27601", prompt)
        self.assertNotIn(case["id"], prompt)
        self.assertNotIn(case["expected"]["blocker"]["error"], prompt)

    def test_http_approval_requires_operator_input_and_persists_receipts(self):
        case = CASES["approval-resume"]
        target = case["expected"]["target"]
        service = Path(__file__).with_name("service.py")
        args = [sys.executable, str(service), "serve", "--case", case["id"], "--run-dir", str(self.run_dir)]
        with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                port_file = self.run_dir / "port"
                self.wait_until(port_file.exists)
                base = f"http://127.0.0.1:{port_file.read_text(encoding='utf-8').strip()}"
                path = f"{base}/v1/objects/{target}"
                status, headers, data = self.http(path)
                self.assertEqual((status, data["value"]), (200, "window-a"))
                self.assertEqual(self.http(path, "PUT", {"value": "window-b"}, headers["ETag"])[0], 428)
                self.assertEqual(self.http(f"{base}/v1/unblock", "POST", {"target": target})[0], 404)
                self.assertEqual(self.checkpoint()["grants"], [])
                status, _, receipt = self.http(f"{base}/v1/messages", "POST", {"recipient": "junior", "body": "Please approve."})
                self.assertEqual((status, receipt["recipient"]), (201, "junior"))
                process.stdin.write(b"unblock\n")
                process.stdin.flush()
                self.wait_until(lambda: self.checkpoint()["grants"] == [target])
                self.assertEqual(self.http(path, "PUT", {"value": "window-b"}, headers["ETag"])[0], 200)
                self.assertEqual(self.http(path)[2]["value"], "window-b")
                events = self.events()
                self.assertEqual([event["seq"] for event in events], list(range(1, 8)))
                self.assertEqual([event["operation"] for event in events], ["read", "write", "unsupported", "message", "operator_unblock", "write", "read"])
                self.assertEqual(self.checkpoint()["messages"][0]["seq"], receipt["receipt"])
            finally:
                process.terminate()

    def wait_until(self, condition):
        deadline = monotonic() + 5
        while not condition():
            if monotonic() >= deadline:
                self.fail("Timed out waiting for fixture state")
            sleep(0.01)

    def http(self, url, method="GET", body=None, etag=None):
        headers = {"Content-Type": "application/json"}
        if etag:
            headers["If-Match"] = etag
        data = json.dumps(body).encode() if body is not None else None
        request = Request(url, method=method, data=data, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.headers, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, error.headers, json.load(error)


if __name__ == "__main__":
    unittest.main()
