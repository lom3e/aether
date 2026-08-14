"""Tiny deterministic Ollama-compatible server used by the HITL E2E test."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    request_count = 0

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        Handler.request_count += 1
        has_approval_tool = any(
            tool.get("function", {}).get("name") == "approval_tool"
            for tool in payload.get("tools", [])
        )

        if Handler.request_count == 1 and has_approval_tool:
            response = {
                "model": payload.get("model", "fake-model"),
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "approval-call-1",
                        "function": {"name": "approval_tool", "arguments": {}},
                    }],
                },
                "done": True,
            }
        else:
            response = {
                "model": payload.get("model", "fake-model"),
                "message": {
                    "role": "assistant",
                    "content": "Approval received. The protected action is complete.",
                },
                "done": True,
            }

        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    port = int(sys.argv[1])
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
