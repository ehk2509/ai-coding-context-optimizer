"""Warm project-scoped runtime for native coding-host hook events.

Hooks remain fail-open and correctness does not depend on this process. The first
hook can spawn a private loopback runtime and handle that event directly; later
hooks reuse a cached HookRuntime through bounded authenticated JSON requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .state import state_dir

_MAX_REQUEST_BYTES = 32 * 1024 * 1024
_CLIENT_TIMEOUT_SECONDS = 1.0
_START_GRACE_SECONDS = 10.0


def _project_id(root: Path) -> str:
    """Return an opaque stable project identity."""
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]


def _runtime_dir() -> Path:
    """Return private native-runtime state directory."""
    path = state_dir() / "native-runtime"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def manifest_path(root: Path) -> Path:
    """Return one project's native-runtime manifest path."""
    return _runtime_dir() / f"{_project_id(root)}.json"


def starting_path(root: Path) -> Path:
    """Return one project's startup-throttle marker."""
    return _runtime_dir() / f"{_project_id(root)}.starting"


@dataclass(frozen=True)
class RuntimeEndpoint:
    """Private local native-runtime endpoint."""

    url: str
    token: str
    pid: int
    root_fingerprint: str


class RuntimePool:
    """Cache one HookRuntime per project while project configuration is unchanged."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[int | None, object]] = {}

    @staticmethod
    def _config_stamp(root: Path) -> int | None:
        """Return project config mtime without reading config content."""
        path = root / ".acco.toml"
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None

    def get(self, root: Path):
        """Return a warm HookRuntime, rebuilding after project config changes."""
        resolved = root.resolve()
        key = str(resolved)
        stamp = self._config_stamp(resolved)
        existing = self._entries.get(key)
        if existing is not None and existing[0] == stamp:
            return existing[1]
        from .hook import build_hook_runtime

        runtime = build_hook_runtime(resolved)
        self._entries[key] = (stamp, runtime)
        return runtime


def _read_manifest(root: Path) -> RuntimeEndpoint | None:
    """Read one private endpoint manifest without accepting another project."""
    path = manifest_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    expected = _project_id(root)
    if payload.get("root_fingerprint") != expected:
        return None
    url = payload.get("url")
    token = payload.get("token")
    pid = payload.get("pid")
    if not isinstance(url, str) or not url.startswith("http://127.0.0.1:"):
        return None
    if not isinstance(token, str) or len(token) < 32:
        return None
    if isinstance(pid, bool) or not isinstance(pid, int):
        return None
    return RuntimeEndpoint(url, token, pid, expected)


def request_native_event(
    root: Path,
    host: str,
    event: str,
    payload: dict,
) -> tuple[str, dict | None]:
    """Send one event to a warm runtime and return status plus response."""
    endpoint = _read_manifest(root)
    if endpoint is None:
        return "unavailable", None
    raw = json.dumps(
        {"host": host, "event": event, "payload": payload},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > _MAX_REQUEST_BYTES:
        return "unavailable", None
    request = Request(
        endpoint.url + "/event",
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(raw)),
            "X-ACCO-Runtime-Token": endpoint.token,
        },
    )
    try:
        with urlopen(request, timeout=_CLIENT_TIMEOUT_SECONDS) as response:
            value = json.loads(response.read())
    except TimeoutError:
        return "timeout", None
    except (OSError, URLError, ValueError):
        return "unavailable", None
    if not isinstance(value, dict) or not isinstance(value.get("response"), dict):
        return "unavailable", None
    return "ok", value["response"]


def _launcher_command(root: Path) -> list[str]:
    """Return a command that starts the private runtime with no shell."""
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).absolute()), "__acco-native-runtime", str(root)]
    return [
        str(Path(sys.executable).absolute()),
        "-m",
        "acco.entry",
        "__acco-native-runtime",
        str(root),
    ]


def ensure_runtime_process(root: Path) -> bool:
    """Spawn one warm runtime at most once per startup grace window."""
    root = root.resolve()
    if _read_manifest(root) is not None:
        return False
    marker = starting_path(root)
    now = time.time()
    try:
        if marker.exists() and now - marker.stat().st_mtime < _START_GRACE_SECONDS:
            return False
    except OSError:
        return False
    try:
        marker.write_text(str(os.getpid()), encoding="ascii")
        os.chmod(marker, 0o600)
    except OSError:
        return False

    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(_launcher_command(root), **kwargs)
    except OSError:
        marker.unlink(missing_ok=True)
        return False
    return True


def _write_manifest(root: Path, server: ThreadingHTTPServer, token: str) -> Path:
    """Publish one owner-only endpoint only after the listener is bound."""
    path = manifest_path(root)
    payload = {
        "schema": 1,
        "url": f"http://127.0.0.1:{server.server_address[1]}",
        "token": token,
        "pid": os.getpid(),
        "root_fingerprint": _project_id(root),
        "started_at": int(time.time()),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)
    starting_path(root).unlink(missing_ok=True)
    return path


def _handler_factory(root: Path, token: str, pool: RuntimePool):
    """Build a content-silent authenticated runtime handler."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "AccoNativeRuntime/1"

        def log_message(self, format: str, *args) -> None:
            """Suppress payload and access logs entirely."""
            del format, args

        def _send(self, status: int, payload: dict) -> None:
            raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send(404, {"error": "not_found"})
                return
            self._send(
                200,
                {
                    "ok": True,
                    "root_fingerprint": _project_id(root),
                    "pid": os.getpid(),
                },
            )

        def do_POST(self) -> None:
            if self.path != "/event":
                self._send(404, {"error": "not_found"})
                return
            if not secrets.compare_digest(
                self.headers.get("X-ACCO-Runtime-Token", ""),
                token,
            ):
                self._send(403, {"error": "forbidden"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                self._send(400, {"error": "invalid_length"})
                return
            if length < 0 or length > _MAX_REQUEST_BYTES:
                self._send(413, {"error": "request_too_large"})
                return
            try:
                body = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"error": "invalid_json"})
                return
            if not isinstance(body, dict) or not isinstance(body.get("payload"), dict):
                self._send(400, {"error": "invalid_event"})
                return
            host = str(body.get("host") or "")
            event = str(body.get("event") or "")
            from .native_hooks import _run_native_hook_with_runtime

            try:
                response = _run_native_hook_with_runtime(
                    host,
                    event,
                    body["payload"],
                    runtime=pool.get(root),
                )
            except Exception:
                response = {}
            self._send(200, {"response": response})

    return Handler


def serve_native_runtime(root: Path) -> int:
    """Serve one warm project runtime on a private random loopback port."""
    root = root.resolve()
    if not root.is_dir():
        return 2
    token = secrets.token_hex(32)
    pool = RuntimePool()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _handler_factory(root, token, pool),
    )
    path = _write_manifest(root, server, token)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
        if isinstance(current, dict) and current.get("pid") == os.getpid():
            path.unlink(missing_ok=True)
    return 0
