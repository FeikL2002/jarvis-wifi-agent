#!/usr/bin/env python3
"""Jarvis Wi-Fi Discovery Agent: loopback dashboard and JSON CLI."""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import platform
import secrets
import signal
import sys
import threading
import time
from urllib.parse import urlsplit
import webbrowser

from jarvis_wifi import __version__
from jarvis_wifi.location import LocationController
from jarvis_wifi.scanner import CoreWLANScanner, DemoScanner, ScanError


class Agent:
    def __init__(self, scanner, location, demo=False, cooldown=10):
        self.scanner, self.location = scanner, location
        self.mode = "demo" if demo else "live"
        self.token = secrets.token_urlsafe(32)
        self.cooldown = cooldown
        self.lock = threading.Lock()
        self.scanning = False
        self.last_started = None
        self.last_result = None
        self.error = None
        self.stop = threading.Event()

    def state(self):
        with self.lock:
            remaining = max(0, math.ceil(self.cooldown - (time.monotonic() - self.last_started))) if self.last_started is not None else 0
            return {"mode": self.mode, "version": __version__, "scanning": self.scanning,
                    "last_result": copy.deepcopy(self.last_result), "error": copy.deepcopy(self.error),
                    "cooldown_seconds": remaining, "diagnostics": diagnostics(self.location)}

    def start_scan(self):
        with self.lock:
            if self.scanning:
                return 409, {"error": {"code": "scan_busy", "message": "A scan is already running.", "remediation": "Wait for it to finish."}}
            if self.last_started is not None and time.monotonic() - self.last_started < self.cooldown:
                return 429, {"error": {"code": "scan_cooldown", "message": "Please wait between scans.", "remediation": "Retry when the countdown finishes."}}
            self.scanning, self.error, self.last_started = True, None, time.monotonic()
        threading.Thread(target=self._scan_worker, daemon=True, name="corewlan-scan").start()
        return 202, {"status": "started"}

    def _scan_worker(self):
        try:
            result = self.scanner.scan()
            with self.lock:
                self.last_result = result
        except ScanError as error:
            with self.lock:
                self.error = error.as_dict()
        except Exception as error:
            with self.lock:
                self.error = {"code": "unexpected_error", "message": str(error), "remediation": "Check the Python environment and README; previous results, if any, are stale."}
        finally:
            with self.lock:
                self.scanning = False


def diagnostics(location):
    return {"platform": platform.platform(), "architecture": platform.machine(),
            "python": platform.python_version(), "location": location.snapshot(),
            "api": "CoreWLAN via PyObjC", "bind_address": "127.0.0.1",
            "scan_policy": "User-triggered broadcast discovery only; no network association or credentials."}


def make_server(agent, port=8765):
    static = Path(os.environ.get("RESOURCEPATH", Path(__file__).resolve().parent)) / "static"
    assets = {"/": ("index.html", "text/html; charset=utf-8"),
              "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
              "/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
              "/static/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
              "/static/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8")}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Do not log SSIDs, response bodies, or session tokens.
            pass

        def respond(self, status, payload, content_type="application/json; charset=utf-8"):
            data = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode() if content_type.startswith("application/json") else payload
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def trusted_request(self):
            port = self.server.server_port
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            if self.headers.get("Host") not in hosts or (origin is not None and origin not in {"http://" + host for host in hosts}):
                self.respond(403, {"error": {"code": "untrusted_origin", "message": "Use the local dashboard address."}})
                return False
            return True

        def do_GET(self):
            if not self.trusted_request():
                return
            path = urlsplit(self.path).path
            if path == "/api/state":
                self.respond(200, agent.state())
            elif path == "/api/session":
                self.respond(200, {"token": agent.token})
            elif path in assets:
                filename, mime = assets[path]
                self.respond(200, (static / filename).read_bytes(), mime)
            elif path == "/favicon.ico":
                self.respond(204, b"", "image/x-icon")
            else:
                self.respond(404, {"error": {"code": "not_found", "message": "Unknown route."}})

        def do_POST(self):
            if not self.trusted_request():
                return
            if not secrets.compare_digest(self.headers.get("X-Jarvis-Token", ""), agent.token):
                self.respond(403, {"error": {"code": "invalid_token", "message": "Reload the local dashboard to start a session."}})
                return
            # Neither endpoint accepts arbitrary input or credentials.
            if self.headers.get("Content-Length", "0") != "0" or self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                self.respond(400, {"error": {"code": "unexpected_body", "message": "This endpoint accepts no request body."}})
                return
            path = urlsplit(self.path).path
            if path == "/api/scan":
                status, body = agent.start_scan()
                self.respond(status, body)
            elif path == "/api/location/request":
                if agent.location.request():
                    self.respond(202, {"status": "requested"})
                else:
                    self.respond(409, {"error": {"code": "location_requires_app", "message": "Permission requests require the Mac app build.", "remediation": "See README: build an app with a location purpose string. Proper signing may also be required by macOS."}})
            elif path == "/api/shutdown":
                self.respond(202, {"status": "stopping"})
                agent.stop.set()
            else:
                self.respond(404, {"error": {"code": "not_found", "message": "Unknown route."}})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="Loopback dashboard port (default: 8765)")
    parser.add_argument("--interface", help="Optional Wi-Fi interface name, e.g. en0")
    parser.add_argument("--demo", action="store_true", help="Use explicitly labeled synthetic data; never scan hardware")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scan", action="store_true", help="Run one scan and print JSON, then exit")
    mode.add_argument("--diagnose", action="store_true", help="Print environment and permission status without scanning")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    location = LocationController(demo=args.demo)
    scanner = DemoScanner() if args.demo else CoreWLANScanner(args.interface)
    if args.diagnose:
        print(json.dumps(diagnostics(location), indent=2))
        return 0
    if args.scan:
        try:
            print(json.dumps({"mode": "demo" if args.demo else "live", "result": scanner.scan(),
                              "diagnostics": diagnostics(location)}, indent=2, ensure_ascii=True))
            return 0
        except ScanError as error:
            print(json.dumps({"error": error.as_dict(), "diagnostics": diagnostics(location)}, indent=2))
            return 2
        except Exception as error:
            print(json.dumps({"error": {"code": "unexpected_error", "message": str(error)}}))
            return 2
    agent = Agent(scanner, location, demo=args.demo)
    try:
        server = make_server(agent, args.port)
    except OSError as error:
        print(f"Cannot start local dashboard: {error}. Try --port 8766.", file=sys.stderr)
        return 2
    stop = agent.stop
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="loopback-dashboard")
    thread.start()
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"Jarvis Wi-Fi Discovery Agent {__version__} | {agent.mode.upper()}\n{address}\nPress Control-C to stop. No scans occur until requested.", flush=True)
    if not args.no_browser:
        webbrowser.open(address)
    try:
        while not stop.wait(0.05):
            location.step()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
