"""Loopback HTTP service exposing the stable ACCO SDK contract."""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import sys
from typing import Any

from . import __version__
from .sdk import AccoEngine

_MAX_REQUEST_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class SdkServerConfig:
    """Configure the local SDK bridge used by non-Python clients."""

    root: Path
    bind: str = "127.0.0.1"
    port: int = 8770
    allow_non_loopback: bool = False
    recovery_capacity_bytes: int = 512 * 1024 * 1024

    def validate(self) -> SdkServerConfig:
        """Reject unsafe network exposure and invalid capacity/port values."""
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("SDK server port must be in 1..65535")
        try:
            bind_ip = ipaddress.ip_address(self.bind)
        except ValueError as exc:
            raise ValueError("SDK server bind must be an IP address") from exc
        if not bind_ip.is_loopback and not self.allow_non_loopback:
            raise ValueError(
                "SDK server binds to loopback by default; pass "
                "allow_non_loopback only behind your own access control"
            )
        if self.recovery_capacity_bytes <= 0:
            raise ValueError("recovery_capacity_bytes must be positive")
        root = Path(self.root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"SDK root must be an existing directory: {root}")
        return SdkServerConfig(
            root=root,
            bind=self.bind,
            port=int(self.port),
            allow_non_loopback=bool(self.allow_non_loopback),
            recovery_capacity_bytes=int(self.recovery_capacity_bytes),
        )


class SdkApplication:
    """Dispatch SDK transport requests into one shared in-process ACCO engine."""

    def __init__(self, engine: AccoEngine):
        """Create an SDK application around one project-scoped engine."""
        self.engine = engine

    @staticmethod
    def _options(payload: dict) -> dict[str, Any]:
        """Return a validated options object from one JSON request."""
        options = payload.get("options", {})
        if options is None:
            return {}
        if not isinstance(options, dict):
            raise ValueError("options must be a JSON object")
        return options

    def dispatch(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Dispatch one versioned SDK request and return status plus JSON."""
        body = payload or {}
        if method == "GET" and path == "/v1/health":
            return 200, {
                "schema": 1,
                "status": "ok",
                "version": __version__,
                "root": str(self.engine.root),
            }
        if method != "POST":
            return 405, {"error": "method_not_allowed"}

        if path == "/v1/provider/optimize":
            provider = body.get("provider")
            request_body = body.get("body")
            if not isinstance(provider, str) or not provider.strip():
                raise ValueError("provider must be a nonempty string")
            if not isinstance(request_body, dict):
                raise ValueError("body must be a JSON object")
            return 200, self.engine.optimize_provider_request(
                provider,
                request_body,
                **self._options(body),
            )

        if path == "/v1/context/optimize":
            text = body.get("text")
            if not isinstance(text, str):
                raise ValueError("text must be a string")
            return 200, self.engine.optimize_context(
                text,
                query=str(body.get("query") or ""),
                command=str(body.get("command") or ""),
                **self._options(body),
            )

        if path == "/v1/browser/optimize":
            text = body.get("text")
            if not isinstance(text, str):
                raise ValueError("text must be a string")
            return 200, self.engine.optimize_browser_context(
                text,
                query=str(body.get("query") or ""),
                **self._options(body),
            )

        if path == "/v1/output/optimize":
            text = body.get("text")
            if not isinstance(text, str):
                raise ValueError("text must be a string")
            options = self._options(body)
            if "exit_code" in body:
                options["exit_code"] = body["exit_code"]
            return 200, self.engine.optimize_output(
                text,
                command=str(body.get("command") or ""),
                **options,
            )

        if path == "/v1/middleware/rag":
            documents = body.get("documents")
            if not isinstance(documents, list):
                raise ValueError("documents must be a JSON array")
            return 200, self.engine.optimize_rag(
                documents,
                query=str(body.get("query") or ""),
                **self._options(body),
            )

        if path == "/v1/middleware/api":
            api_payload = body.get("payload")
            if not isinstance(api_payload, (dict, list)):
                raise ValueError("payload must be a JSON object or array")
            return 200, self.engine.optimize_api_payload(
                api_payload,
                query=str(body.get("query") or ""),
                **self._options(body),
            )

        if path == "/v1/middleware/database":
            rows = body.get("rows")
            if not isinstance(rows, list):
                raise ValueError("rows must be a JSON array")
            columns = body.get("columns")
            if columns is not None and not isinstance(columns, list):
                raise ValueError("columns must be a JSON array")
            return 200, self.engine.optimize_database_rows(
                rows,
                query=str(body.get("query") or ""),
                columns=columns,
                **self._options(body),
            )

        if path == "/v1/execute":
            code = body.get("code")
            files = body.get("files")
            if not isinstance(code, str):
                raise ValueError("code must be a string")
            if not isinstance(files, list):
                raise ValueError("files must be a JSON array")
            return 200, self.engine.execute(
                code,
                [str(value) for value in files],
                **self._options(body),
            )

        if path == "/v1/context-budget":
            prompt = body.get("prompt")
            if not isinstance(prompt, str):
                raise ValueError("prompt must be a string")
            options = self._options(body)
            total_tokens = options.pop("total_tokens", body.get("total_tokens"))
            if not isinstance(total_tokens, int) or isinstance(total_tokens, bool):
                raise ValueError("total_tokens must be an integer")
            return 200, self.engine.plan_context_budget(
                prompt,
                total_tokens=total_tokens,
                **options,
            )

        if path == "/v1/route":
            prompt = body.get("prompt")
            if not isinstance(prompt, str):
                raise ValueError("prompt must be a string")
            return 200, self.engine.route_model(
                prompt,
                **self._options(body),
            )

        if path == "/v1/recover":
            handle = body.get("handle")
            if not isinstance(handle, str):
                raise ValueError("handle must be a string")
            try:
                return 200, self.engine.recover(handle)
            except KeyError:
                return 404, {"error": "recovery_not_found", "handle": handle}

        return 404, {"error": "not_found"}


def _handler_factory(application: SdkApplication):
    """Create an HTTP handler bound to one SDK application."""

    class Handler(BaseHTTPRequestHandler):
        """Serve a minimal local JSON API without logging request content."""

        server_version = "AccoSdkServer/1"

        def log_message(self, format: str, *args) -> None:
            """Emit terse access metadata only."""
            print(
                "acco sdk: " + format % args,
                file=sys.stderr,
            )

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            """Serialize one JSON response."""
            raw = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _request_payload(self) -> dict:
            """Read one bounded JSON-object request body."""
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ValueError("Content-Length required")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if length < 0 or length > _MAX_REQUEST_BYTES:
                raise ValueError("request body too large")
            content_type = self.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                raise ValueError("Content-Type must be application/json")
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("invalid JSON request body") from exc
            if not isinstance(payload, dict):
                raise ValueError("JSON request body must be an object")
            return payload

        def _dispatch(self, method: str) -> None:
            """Dispatch one GET or POST request with bounded error messages."""
            try:
                payload = None if method == "GET" else self._request_payload()
                status, result = application.dispatch(
                    method,
                    self.path.split("?", 1)[0],
                    payload,
                )
            except (TypeError, ValueError) as exc:
                self._send(400, {"error": "invalid_request", "message": str(exc)})
                return
            except Exception as exc:
                print(f"acco sdk internal error: {type(exc).__name__}", file=sys.stderr)
                self._send(500, {"error": "internal_error"})
                return
            self._send(status, result)

        def do_GET(self) -> None:
            """Handle one GET request."""
            self._dispatch("GET")

        def do_POST(self) -> None:
            """Handle one POST request."""
            self._dispatch("POST")

    return Handler


def run_sdk_server(config: SdkServerConfig) -> None:
    """Run the local SDK bridge until interrupted."""
    config = config.validate()
    application = SdkApplication(
        AccoEngine(
            config.root,
            recovery_capacity_bytes=config.recovery_capacity_bytes,
        )
    )
    server = ThreadingHTTPServer(
        (config.bind, config.port),
        _handler_factory(application),
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
