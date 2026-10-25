"""Stdio MCP server with one stub tool, ``request_decision``, for the scope eval.

A session under test asks the user through this tool the way a project thread
posts a decision card. The tool records nothing and answers that the card is
posted, so the grader counts asks from the session's own tool calls.
"""

import json
import sys
from typing import TextIO

from scope_eval_support.config.constants import (
    ALL_DECISION_INPUT_SCHEMA,
    DECISION_ACK_TEXT,
    DECISION_TOOL_DESCRIPTION,
    DECISION_TOOL_NAME,
    JSON_RPC_METHOD_NOT_FOUND_CODE,
    JSON_RPC_VERSION,
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
)


def _payload_by_method() -> dict[str, dict[str, object]]:
    return {
        "initialize": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
        },
        "tools/list": {
            "tools": [
                {
                    "name": DECISION_TOOL_NAME,
                    "description": DECISION_TOOL_DESCRIPTION,
                    "inputSchema": ALL_DECISION_INPUT_SCHEMA,
                }
            ]
        },
        "tools/call": {"content": [{"type": "text", "text": DECISION_ACK_TEXT}]},
    }


def _unknown_method_reply(request_id: object, method: object) -> dict[str, object]:
    return {
        "jsonrpc": JSON_RPC_VERSION,
        "id": request_id,
        "error": {
            "code": JSON_RPC_METHOD_NOT_FOUND_CODE,
            "message": f"unknown method {method}",
        },
    }


def reply_for(request_by_field: dict[str, object]) -> dict[str, object] | None:
    """Return the JSON-RPC reply for one request, or None for a notification.

    ::

        {"id": 1, "method": "tools/list"} -> {"id": 1, "result": {"tools": [request_decision]}}
        {"method": "notifications/initialized"} -> None

    Args:
        request_by_field: One parsed JSON-RPC message.

    Returns:
        The reply to write, or None when the message needs none.
    """
    if "id" not in request_by_field:
        return None
    method = request_by_field.get("method")
    payload_by_method = _payload_by_method()
    if method not in payload_by_method:
        return _unknown_method_reply(request_by_field["id"], method)
    return {
        "jsonrpc": JSON_RPC_VERSION,
        "id": request_by_field["id"],
        "result": payload_by_method[method],
    }


def _send_reply(reply_by_field: dict[str, object], protocol_stream: TextIO) -> None:
    protocol_stream.write(json.dumps(reply_by_field) + "\n")
    protocol_stream.flush()


def main() -> int:
    """Answer JSON-RPC lines on standard input until it closes.

    Returns:
        Zero once standard input closes.
    """
    for each_line in sys.stdin:
        if not each_line.strip():
            continue
        reply = reply_for(json.loads(each_line))
        if reply is not None:
            _send_reply(reply, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
