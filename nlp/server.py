"""Small local operator interface; no vehicle control or persistent state."""

import ipaddress
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pydantic import Field, ValidationError

from nlp.client import NLPError
from nlp.models import Mission, StrictModel
from nlp.parser import IntentParser


class IntentRequest(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    current_mission: Mission | None = None


ASSETS = {
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/style.css": ("style.css", "text/css"),
}


def create_server(parser: IntentParser, bind: str, port: int) -> ThreadingHTTPServer:
    try:
        address = ipaddress.IPv4Address(bind)
        if address.is_unspecified or not 0 <= port <= 65535:
            raise ValueError
    except (ValueError, TypeError) as error:
        raise NLPError("invalid_config", "Bind to a specific IPv4 address and port 0–65535.") from error

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def reply(self, status, body, content_type="application/json"):
            content = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def fail(self, status, code, message):
            self.reply(status, {"error": {"code": code, "message": message}})

        def valid_host(self):
            hosts = {f"{bind}:{self.server.server_port}"}
            if address.is_loopback:
                hosts.add(f"localhost:{self.server.server_port}")
            if self.headers.get("Host") not in hosts:
                self.fail(403, "forbidden", "Use the configured interface address.")
                return False
            return True

        def do_GET(self):
            if not self.valid_host():
                return
            asset = ASSETS.get(self.path)
            if asset is None:
                self.fail(404, "not_found", "Unknown resource.")
                return
            name, content_type = asset
            self.reply(200, (Path(__file__).parent / "web" / name).read_bytes(), content_type)

        def do_POST(self):
            if not self.valid_host():
                return
            if self.path != "/api/interpret":
                self.fail(404, "not_found", "Unknown resource.")
                return
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{self.headers['Host']}":
                self.fail(403, "forbidden", "Cross-origin requests are not allowed.")
                return
            if self.headers.get_content_type() != "application/json":
                self.fail(415, "invalid_input", "Send application/json.")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or self.headers.get("Transfer-Encoding"):
                    raise ValueError
                if length > 65536:
                    self.fail(413, "invalid_input", "Request body is too large.")
                    return
                request = IntentRequest.model_validate_json(self.rfile.read(length))
            except (ValueError, ValidationError, OSError):
                self.fail(400, "invalid_input", "Provide intent text (1–4000 characters) and an optional valid current_mission.")
                return
            if not self.server.inference_lock.acquire(blocking=False):
                self.fail(503, "busy", "Another intent is being interpreted. Try again shortly.")
                return
            try:
                result = parser.parse(request.text, current_mission=request.current_mission)
                self.reply(200, result.model_dump())
            except NLPError as error:
                status = 400 if error.code == "invalid_input" else 502
                if error.code in ("backend_unavailable", "model_unavailable"):
                    status = 503
                self.fail(status, error.code, str(error))
            finally:
                self.server.inference_lock.release()

        def log_message(self, *args):
            # Intent text stays in the response; callers choose their logging policy.
            pass

    try:
        server = ThreadingHTTPServer((bind, port), Handler)
    except OSError as error:
        raise NLPError("invalid_config", "Cannot bind the browser server. Check the interface and port.") from error
    server.inference_lock = threading.Lock()
    return server


def run_server(parser: IntentParser, bind: str, port: int):
    with create_server(parser, bind, port) as server:
        print(f"Leader's Intent: http://{bind}:{server.server_port}", file=sys.stderr)
        server.serve_forever()
