import argparse
import json
import logging
import sys
from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from time import monotonic
from typing import TextIO
from urllib.parse import unquote, urlsplit

from config.fixture_constants import (
    ALL_CAPABILITY_ROUTE_PREFIX_SEGMENTS,
    ALL_MESSAGE_ROUTE_SEGMENTS,
    ALL_OBJECT_ROUTE_PREFIX_SEGMENTS,
    API_GUIDE,
    CASES_PATH,
    LOOPBACK,
    LOOPBACK_URL_PREFIX,
    MILLISECONDS_PER_SECOND,
)


FixtureCase = dict[str, object]
HttpReply = tuple[int, dict[str, object], dict[str, str]]
logger = logging.getLogger(__name__)


def load_cases(cases_path: Path = CASES_PATH) -> dict[str, FixtureCase]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]
    return {case["id"]: case for case in cases}


def render_prompt(case: FixtureCase, base_url: str) -> str:
    guide = API_GUIDE.format(base_url=base_url.rstrip("/"), recipient=case["expected"]["recipient"])
    return f"{case['prompt']}\n\n{guide}\n"


class Fixture:
    def __init__(self, case: FixtureCase, run_dir: Path) -> None:
        self.case = case
        self.run_dir = run_dir
        self.lock = Lock()
        self.started = monotonic()
        self.seq = 0
        self.state = {
            "case_id": case["id"],
            "objects": deepcopy(case["objects"]),
            "messages": [],
            "grants": [],
        }
        self.run_dir.mkdir(mode=0o700, parents=True)
        self.events_path = self.run_dir / "events.jsonl"
        self.events_path.touch()
        self.save_state()

    def save_state(self) -> None:
        next_path = self.run_dir / "state.next"
        next_path.write_text(json.dumps(self.state, sort_keys=True) + "\n", encoding="utf-8")
        next_path.replace(self.run_dir / "state.json")

    def record(self, operation: str, target: str, status: int, **details: object) -> dict[str, object]:
        """Append a timestamped receipt.

        Args:
            operation: Fixture action that produced the receipt.
            target: Record or recipient addressed by the action.
            status: HTTP status associated with the action.
            **details: Additional receipt fields for the action.

        Returns:
            The appended event, including its sequence and timestamp.
        """
        self.seq += 1
        event = {
            "seq": self.seq,
            "elapsed_ms": round((monotonic() - self.started) * MILLISECONDS_PER_SECOND),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "target": target,
            "status": status,
            **details,
        }
        with self.events_path.open("a", encoding="utf-8") as events:
            events.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def failure(
        self, operation: str, target: str, status: int, error: str, **details: object
    ) -> HttpReply:
        self.record(operation, target, status, error=error, **details)
        return status, {"error": error, "target": target, **details}, {}

    def object_request(
        self, operation: str, target: str, if_match: str | None = None, body: object = None
    ) -> HttpReply:
        """Read a record, check access, or publish a versioned update.

        Args:
            operation: Read, capability, or write action.
            target: Requested record name, which may be an alias.
            if_match: Current ETag supplied by a write request.
            body: Decoded JSON supplied by a write request.

        Returns:
            The HTTP status, JSON payload, and headers for the action.
        """
        canonical = self.case["aliases"].get(target, target)
        current = self.state["objects"].get(canonical)
        if current is None:
            return self.failure(operation, target, 404, "Record not found")
        etag = f'"{current["version"]}"'
        if operation == "read":
            self.record(operation, target, HTTPStatus.OK, result_version=current["version"])
            return HTTPStatus.OK, {"target": target, **current}, {"ETag": etag}

        if operation == "write" and canonical != target:
            return self.failure(operation, target, 409, "Publication route retired", replacement=canonical)
        restriction = self.case["restrictions"].get(canonical)
        if restriction and canonical not in self.state["grants"]:
            return self.failure(operation, target, **restriction)
        if operation == "capability":
            self.record(operation, target, HTTPStatus.OK)
            return HTTPStatus.OK, {"target": target, "publish": True}, {}
        if if_match != etag:
            return self.failure(operation, target, 412, "If-Match must equal the current ETag")
        if not isinstance(body, dict) or set(body) != {"value"}:
            return self.failure(operation, target, 400, "Expected a JSON object with one value field")

        updated = {"value": body["value"], "version": current["version"] + 1}
        self.state["objects"][canonical] = updated
        self.save_state()
        self.record(operation, target, HTTPStatus.OK, value=updated["value"], result_version=updated["version"])
        return HTTPStatus.OK, {"target": target, **updated}, {"ETag": f'"{updated["version"]}"'}

    def message_request(self, body: object) -> HttpReply:
        """Deliver a message to the requested fixture recipient.

        Args:
            body: Decoded JSON with recipient and message fields.

        Returns:
            The HTTP status, message receipt or error, and headers.
        """
        if not isinstance(body, dict) or set(body) != {"recipient", "body"}:
            return self.failure("message", "", 400, "Expected recipient and body fields")
        recipient, message = body["recipient"], body["body"]
        if not all(isinstance(field, str) and field.strip() for field in (recipient, message)):
            return self.failure("message", "", 400, "Expected nonempty recipient and body strings")
        event = self.record("message", recipient, HTTPStatus.CREATED, recipient=recipient, body=message)
        keys = ("recipient", "body", "seq", "elapsed_ms")
        self.state["messages"].append({key: event[key] for key in keys})
        self.save_state()
        return HTTPStatus.CREATED, {"receipt": event["seq"], "recipient": recipient}, {}

    def request(self, method: str, path: str, if_match: str | None, body: object) -> HttpReply:
        """Dispatch a request under the case state lock.

        Args:
            method: Inbound HTTP method.
            path: Inbound request path.
            if_match: Value of the request's If-Match header.
            body: Decoded JSON request payload, if provided.

        Returns:
            The HTTP status, JSON payload, and headers from the routed action.
        """
        parts = tuple(urlsplit(path).path.split("/"))
        target = unquote(parts[-1])
        route_prefix = parts[:-1]
        is_object_route = bool(target) and route_prefix == ALL_OBJECT_ROUTE_PREFIX_SEGMENTS
        with self.lock:
            if is_object_route and method == "GET":
                return self.object_request("read", target)
            if is_object_route and method == "PUT":
                return self.object_request("write", target, if_match, body)
            if target and route_prefix == ALL_CAPABILITY_ROUTE_PREFIX_SEGMENTS and method == "GET":
                return self.object_request("capability", target)
            if parts == ALL_MESSAGE_ROUTE_SEGMENTS and method == "POST":
                return self.message_request(body)
            return self.failure("unsupported", path, 404, "No such operation", method=method)

    def operator_input(self) -> None:
        """Receive the operator's scoped unblock command from stdin."""
        target = self.case["expected"]["resume"]["target"]
        for each_line in sys.stdin:
            if each_line.strip() == "unblock":
                self._grant(target)

    def _grant(self, target: str) -> None:
        with self.lock:
            if target in self.state["grants"]:
                return
            self.state["grants"].append(target)
            self.save_state()
            self.record("operator_unblock", target, HTTPStatus.OK)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, pattern: str, *log_fields: object) -> None:
        logger.debug(pattern, *log_fields)

    def body(self) -> object:
        """Read a bounded JSON request body.

        Returns:
            The decoded payload, or None when missing or invalid.
        """
        body_limit = 65536
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if 0 < length <= body_limit:
                return json.loads(self.rfile.read(length))
        except ValueError:
            pass
        return None

    def send_fixture_reply(self) -> None:
        status, payload, headers = self.server.fixture.request(
            self.command,
            self.path,
            self.headers.get("If-Match"),
            self.body(),
        )
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        for each_header, each_header_content in headers.items():
            self.send_header(each_header, each_header_content)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(encoded)

    do_GET = do_HEAD = do_PUT = do_POST = do_PATCH = do_DELETE = do_OPTIONS = send_fixture_reply


def _serve(
    case: FixtureCase, run_dir: Path, port: int, fixture_type: type[Fixture], stream: TextIO
) -> None:
    with ThreadingHTTPServer((LOOPBACK, port), Handler) as server:
        server.fixture = fixture_type(case, run_dir)
        if "resume" in case["expected"]:
            Thread(target=server.fixture.operator_input, daemon=True).start()
        port = server.server_address[1]
        port_path = run_dir / "port.next"
        port_path.write_text(f"{port}\n", encoding="utf-8")
        port_path.replace(run_dir / "port")
        stream.write(f"{LOOPBACK_URL_PREFIX}{port}\n")
        stream.flush()
        server.serve_forever()


def main(stream: TextIO, cases_path: Path = CASES_PATH, fixture_type: type[Fixture] = Fixture) -> None:
    """Run the requested fixture command.

    Args:
        stream: Destination for the prompt or listener address.
        cases_path: Dataset used by the command.
        fixture_type: Fixture implementation used by the listener.
    """
    cases = load_cases(cases_path)
    parser = argparse.ArgumentParser(description="Synthetic Launch Ledger service for the Codex blocker eval")
    commands = parser.add_subparsers(dest="command", required=True)
    service = commands.add_parser("serve")
    service.add_argument("--case", choices=cases, required=True)
    service.add_argument("--run-dir", required=True, type=Path)
    service.add_argument("--port", default=0, type=int)
    prompt = commands.add_parser("prompt")
    prompt.add_argument("--case", choices=cases, required=True)
    prompt.add_argument("--base-url", required=True)
    options = parser.parse_args()
    case = cases[options.case]
    if options.command == "prompt":
        stream.write(render_prompt(case, options.base_url))
    else:
        _serve(case, options.run_dir, options.port, fixture_type, stream)


if __name__ == "__main__":
    main(sys.stdout)
