"""Local test page for the v4 engine. Standard library only.

    python -m simulation.engine_v4.devui            # http://127.0.0.1:8765
    python -m simulation.engine_v4.devui --port 9000 --no-browser

A development tool, not the game frontend. It listens on 127.0.0.1 only.
"""
from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import api

PAGE = Path(__file__).with_name("devui.html")
MAX_BODY = 1_000_000


class Handler(BaseHTTPRequestHandler):
    server_version = "EngineV4DevUI/0.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/catalog":
            self._json(*api.handle_catalog_request())
        elif path == "/api/scenarios":
            self._json(*api.handle_scenarios_request())
        else:
            self._json(404, {"error": {"code": "not_found", "message": "No such page.", "field": None}})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        handler = {"/api/run": api.handle_run_request, "/api/recommend": api.handle_recommend_request}.get(path)
        if handler is None:
            self._json(404, {"error": {"code": "not_found", "message": "No such endpoint.", "field": None}})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("body too large")
            body = json.loads(self.rfile.read(length) or b"null")
        except (ValueError, json.JSONDecodeError):
            self._json(422, {"error": {"code": "invalid_request", "message": "Body must be valid JSON.",
                                       "field": None}})
            return
        self._json(*handler(body))

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        pass


def make_server(port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local test page for the v4 simulation engine.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = make_server(args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Engine v4 test page: {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
