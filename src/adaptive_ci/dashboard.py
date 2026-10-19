from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from .simulation import run_simulation

LIMITS = {"tests": (4, 200), "builds": (2, 500), "iterations": (1, 1000)}


def _params(query: str) -> dict:
    raw = {key: values[0] for key, values in parse_qs(query).items()}
    params = {
        "test_count": int(raw.get("tests", 25)),
        "builds": int(raw.get("builds", 40)),
        "budget": float(raw.get("budget", 60)),
        "seed": int(raw.get("seed", 42)),
        "iterations": int(raw.get("iterations", 40)),
    }
    for name, key in (("tests", "test_count"), ("builds", "builds"), ("iterations", "iterations")):
        low, high = LIMITS[name]
        if not low <= params[key] <= high:
            raise ValueError(f"{name} must be between {low} and {high}")
    return params


class _Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path in {"/", "/index.html"}:
            page = files("adaptive_ci").joinpath("dashboard.html").read_bytes()
            self._send(200, page, "text/html; charset=utf-8")
        elif url.path == "/api/simulate":
            try:
                report = run_simulation(**_params(url.query))
                self._send(200, json.dumps(report).encode(), "application/json")
            except ValueError as exc:
                self._send(400, json.dumps({"error": str(exc)}).encode(), "application/json")
        elif url.path == "/api/shop":
            try:
                from .shop_demo import load_shop_run

                self._send(200, json.dumps(load_shop_run()).encode(), "application/json")
            except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
                self._send(400, json.dumps({"error": str(exc)}).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/shop/run":
            self._send(404, b"not found", "text/plain")
            return
        try:
            from .shop_demo import load_shop_run, run_shop_demo

            code = run_shop_demo()
            report = load_shop_run()
            report["exit_code"] = code
            self._send(200, json.dumps(report).encode(), "application/json")
        except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, json.dumps({"error": str(exc)}).encode(), "application/json")

    def log_message(self, *_args) -> None:
        pass


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"Adaptive CI dashboard: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
