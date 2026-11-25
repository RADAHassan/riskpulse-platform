"""Minimal Alertmanager webhook receiver for demos and e2e tests: logs alerts and exposes them on GET /alerts."""

import json
import sys
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer

RECEIVED: deque = deque(maxlen=200)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server API
        length = min(int(self.headers.get("Content-Length", "0")), 1_000_000)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return
        for alert in payload.get("alerts", []):
            entry = {
                "channel": self.path.strip("/") or "default",
                "status": alert.get("status"),
                "alertname": alert.get("labels", {}).get("alertname"),
                "severity": alert.get("labels", {}).get("severity"),
                "application": alert.get("labels", {}).get("application"),
                "summary": alert.get("annotations", {}).get("summary"),
            }
            RECEIVED.append(entry)
            print(json.dumps(entry), flush=True)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        body = json.dumps(list(RECEIVED)).encode()
        self.send_response(200 if self.path.startswith("/alerts") else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()  # noqa: S104 - container-internal service
