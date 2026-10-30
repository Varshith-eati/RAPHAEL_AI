"""Local HTTP transport: routing, browser boundary checks and JSON encoding only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import secrets
import socket
import threading
from urllib.parse import urlsplit

from .errors import AppError
from .validation import MAX_RECORDING_BYTES

LOG = logging.getLogger("raphael.http")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/voice.js": ("voice.js", "text/javascript; charset=utf-8"),
          "/microphone.js": ("microphone.js", "text/javascript; charset=utf-8"),
          "/live-call.js": ("live-call.js", "text/javascript; charset=utf-8"),
          "/laptop.js": ("laptop.js", "text/javascript; charset=utf-8"),
          "/recorder-worklet.js": ("recorder-worklet.js", "text/javascript; charset=utf-8"),
          "/styles.css": ("styles.css", "text/css; charset=utf-8"),
          "/original": ("original-interface.html", "text/html; charset=utf-8"),
          "/sample.wav": ("sample.wav", "audio/wav")}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, app, port=None, require_bootstrap=False):
        self.app = app
        self.require_bootstrap = require_bootstrap
        self.token = secrets.token_urlsafe(32)
        self._slots = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", app.config.server.port if port is None else port), Handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "Raphael"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(self.server.app.config.server.request_timeout_seconds)

    def log_message(self, *_):
        pass

    def _reply(self, status, data, mime="application/json; charset=utf-8"):
        content = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        for key, value in {"Content-Type": mime, "Content-Length": str(len(content)),
                           "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                           "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionError, socket.timeout):
            pass

    def _boundary(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if len(self.headers.get_all("Host", [])) != 1 or self.headers.get("Host") not in hosts:
            raise AppError("Invalid host.", 403, "invalid_host")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in hosts}:
            raise AppError("Cross-origin request blocked.", 403, "invalid_origin")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise AppError("Cross-site request blocked.", 403, "invalid_origin")

    def _authenticate(self):
        supplied = self.headers.get("X-Raphael-Token", "").encode("utf-8")
        if not secrets.compare_digest(supplied, self.server.token.encode("ascii")):
            raise AppError("Reload Raphael to reconnect.", 403, "invalid_token")

    def _read_body(self, limit):
        self._body_started = True
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
            raise AppError("Send one Content-Length header.")
        try:
            length = int(self.headers["Content-Length"])
            if length > limit:
                # Drain only a bounded oversized frame so Windows can deliver the 413
                # instead of resetting a connection with a small unread request body.
                if length <= limit + 4096: self.rfile.read(length)
                raise AppError("Request too large or empty.", 413, "body_size")
            if length <= 0:
                raise AppError("Request too large or empty.", 413, "body_size")
            content = self.rfile.read(length)
            if len(content) != length:
                raise ValueError("Incomplete body")
            return content
        except ValueError:
            raise AppError("Incomplete or invalid request body.") from None

    def _json_body(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise AppError("Expected JSON.", 415, "unsupported_media")
        content = self._read_body(self.server.app.config.server.max_body_bytes)
        try:
            def reject_constant(_):
                raise ValueError("Nonfinite JSON")
            payload = json.loads(content, parse_constant=reject_constant)
            if not isinstance(payload, dict):
                raise ValueError("Object required")
            return payload
        except (ValueError, UnicodeError, RecursionError):
            raise AppError("Invalid JSON request.") from None

    def _dispatch(self, method):
        self._body_started = False
        try:
            self._boundary()
            route = urlsplit(self.path).path
            app = self.server.app
            if method == "GET":
                if route == "/api/status":
                    if self.server.require_bootstrap: self._authenticate()
                    self._reply(200, {**app.status(), "token": self.server.token})
                    return
                if route == "/api/health":
                    health = app.jobs.health()
                    ready = health["chat"]["state"] == "ready"
                    self._reply(200 if ready else 503, {"ready": ready, "engines": health})
                    return
                if route.startswith("/api/"):
                    self._authenticate()
                if route == "/api/profile":
                    self._reply(200, app.profiles.get().as_dict())
                    return
                if route == '/api/interaction':
                    self._reply(200, app.settings.get())
                    return
                if route == '/api/performance':
                    self._reply(200, app.performance.report())
                    return
                if route == '/api/laptop':
                    self._reply(200, {**app.laptop.status(), 'approvals': app.laptop.approvals.list()})
                    return
                if route == '/api/laptop/system':
                    from .contracts import Cancellation
                    self._reply(200, app.laptop.execute('system_info', {}, Cancellation()))
                    return
                if route.startswith("/api/jobs/"):
                    self._reply(200, app.jobs.snapshot(route.removeprefix("/api/jobs/")))
                    return
                if route.startswith("/api/audio/"):
                    self._reply(200, app.jobs.audio(route.removeprefix("/api/audio/")), "audio/wav")
                    return
                if route in STATIC:
                    filename, mime = STATIC[route]
                    target = app.config.root / "web" / filename
                    if target.is_file():
                        self._reply(200, target.read_bytes(), mime)
                        return
            elif method == "POST":
                self._authenticate()
                if route == "/api/transcribe":
                    if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "audio/wav":
                        raise AppError("Expected WAV audio.", 415, "unsupported_media")
                    audio = self._read_body(MAX_RECORDING_BYTES)
                    self._reply(202, {"id": app.submit_transcription(audio, self.headers.get("X-Raphael-Language"))})
                    return
                payload = self._json_body()
                if route == '/api/interaction':
                    self._reply(200, app.update_settings(payload))
                    return
                if route == '/api/performance':
                    from .realtime.metrics import STAGES
                    import math
                    if (set(payload) != {'stage', 'seconds', 'kind'} or not isinstance(payload['stage'], str) or payload['stage'] not in STAGES
                        or payload['kind'] not in ('browser', 'desktop') or type(payload['seconds']) not in (float, int)
                        or not math.isfinite(payload['seconds']) or not 0 <= payload['seconds'] <= 3600):
                        raise AppError('Invalid performance measurement.')
                    app.performance.record(**payload)
                    self._reply(200, {'saved': True})
                    return
                if route == '/api/desktop':
                    if not app.desktop: raise AppError('Open Launch-Desktop.cmd for the desktop companion.', 409)
                    if set(payload) != {'action'} or payload['action'] not in ('settings', 'activate', 'dismiss', 'exit', 'web_closed', 'web_heartbeat', 'text_start', 'text_end', 'mute'):
                        raise AppError('Unknown desktop action.')
                    app.desktop.request_action(payload['action'])
                    self._reply(202, {'accepted': True})
                    return
                if route == '/api/laptop/access':
                    if set(payload) != {'enabled'}:
                        raise AppError('Send only the access setting.')
                    self._reply(200, app.laptop.set_enabled(payload['enabled']))
                    return
                if route == '/api/laptop/open':
                    from .contracts import Cancellation
                    self._reply(200, app.laptop.execute('open_app', payload, Cancellation()))
                    return
                if route == '/api/laptop/files':
                    from .contracts import Cancellation
                    if set(payload)!={'action','path'} or payload['action'] not in ('browse_folder','read_file'):
                        raise AppError('Choose Browse folder or Read file with a path.')
                    self._reply(200,app.laptop.execute(payload['action'],{'path':payload['path']},Cancellation()))
                    return
                if route.startswith('/api/laptop/approvals/'):
                    if set(payload) != {'decision'}:
                        raise AppError('Only the reviewed proposal can be approved.')
                    self._reply(200, app.laptop.approvals.decide(route.removeprefix('/api/laptop/approvals/'), payload['decision']))
                    return
                if route == "/api/chat":
                    self._reply(202, {"id": app.submit_chat(payload)})
                    return
                if route == "/api/speak":
                    self._reply(202, {"id": app.submit_speech(payload)})
                    return
                if route == "/api/profile":
                    self._reply(200, app.save_profile(payload))
                    return
                if route.startswith("/api/cancel/"):
                    app.jobs.cancel(route.removeprefix("/api/cancel/"))
                    self._reply(200, {"state": "cancelled"})
                    return
                if route == "/api/shutdown":
                    self._reply(200, {"state": "stopping"})
                    if app.desktop:
                        app.desktop.request_action('exit')
                        return
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
            raise AppError("Not found.", 404, "not_found")
        except AppError as error:
            # A small unread POST can make Windows reset the socket before the
            # client receives a rejection. Drain bounded data, never execute it.
            if method == 'POST' and not self._body_started and not self.headers.get('Transfer-Encoding') and len(self.headers.get_all('Content-Length', [])) == 1:
                try: length = int(self.headers['Content-Length'])
                except ValueError: length = 0
                if 0 < length <= 4096:
                    timeout = self.connection.gettimeout()
                    try:
                        self.connection.settimeout(.1); self.rfile.read(length)
                    except (OSError, ValueError): pass
                    finally: self.connection.settimeout(timeout)
            self._reply(error.status, {"error": str(error), "code": error.code})
        except (socket.timeout, TimeoutError):
            self._reply(408, {"error": "Request timed out.", "code": "request_timeout"})
        except Exception as error:
            LOG.error("request_failed exception=%s", type(error).__name__)
            self._reply(500, {"error": "The request could not be completed. Check runtime/raphael.log.",
                              "code": "internal_error"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")
