"""Opt-in local HTTP reverse proxy for provider-request optimization."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import ipaddress
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .provider_boundary import SUPPORTED_PROVIDERS
from .provider_cost import PROVIDER_MODEL_ROUTING_MODES
from .provider_transform import ProviderTransformResult, transform_provider_request
from .provider_usage import ProviderUsageObserver

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
_MAX_REQUEST_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class ProviderProxyConfig:
    """Configure one local provider proxy instance."""

    root: Path
    upstream: str
    provider: str = "auto"
    bind: str = "127.0.0.1"
    port: int = 8765
    compress_schemas: bool = True
    compress_tool_results: bool = True
    deduplicate_history: bool = True
    tool_result_min_tokens: int = 800
    timeout_seconds: float = 120.0
    allow_non_loopback: bool = False
    prefix_tracking: bool = True
    usage_telemetry: bool = True
    model_routing_mode: str = "off"
    model_routing_calibration_file: str = ".acco.routing-calibration.json"
    model_routing_min_savings: float = 0.05
    instance_id: str = ""
    context_budget_total_tokens: int | None = None
    provider_cache_mode: str = "plan"
    provider_cache_expected_reuses: int = 2

    def validate(self) -> ProviderProxyConfig:
        """Reject unsafe binding/upstream combinations before serving."""
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("proxy port must be in 1..65535")
        if self.provider.strip().lower() not in SUPPORTED_PROVIDERS:
            raise ValueError(
                "proxy provider must be one of: "
                + ", ".join(SUPPORTED_PROVIDERS)
            )
        try:
            bind_ip = ipaddress.ip_address(self.bind)
        except ValueError as exc:
            raise ValueError("proxy bind must be an IP address") from exc
        if not bind_ip.is_loopback and not self.allow_non_loopback:
            raise ValueError(
                "provider proxy binds to loopback by default; "
                "pass allow_non_loopback only behind your own access control"
            )
        parsed = urlparse(self.upstream)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError("proxy upstream must be an absolute http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("proxy upstream URL must not contain credentials")
        if parsed.scheme == "http":
            host = parsed.hostname or ""
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = host in {"localhost"}
            if not local:
                raise ValueError("plain HTTP upstream is allowed only for localhost")
        if self.timeout_seconds <= 0:
            raise ValueError("proxy timeout_seconds must be positive")
        if self.model_routing_mode.strip().lower() not in PROVIDER_MODEL_ROUTING_MODES:
            raise ValueError(
                "provider model routing mode must be one of: "
                + ", ".join(PROVIDER_MODEL_ROUTING_MODES)
            )
        if not 0 <= float(self.model_routing_min_savings) <= 1:
            raise ValueError("provider model routing min savings must be between 0 and 1")
        if (
            self.context_budget_total_tokens is not None
            and int(self.context_budget_total_tokens) < 1000
        ):
            raise ValueError("context budget total tokens must be at least 1000")
        if self.provider_cache_mode.strip().lower() not in {"off", "plan", "apply"}:
            raise ValueError("provider_cache_mode must be one of: off, plan, apply")
        if (
            isinstance(self.provider_cache_expected_reuses, bool)
            or int(self.provider_cache_expected_reuses) < 0
        ):
            raise ValueError("provider_cache_expected_reuses must be nonnegative")
        return self


@dataclass(frozen=True)
class TransformedRequest:
    """Serialized provider request plus transformation metadata."""

    body: bytes
    metadata: dict


def transform_request_bytes(
    config: ProviderProxyConfig,
    raw: bytes,
    *,
    content_type: str,
    request_path: str = "",
) -> TransformedRequest:
    """Transform a JSON request body or pass unsupported payloads through."""
    if len(raw) > _MAX_REQUEST_BYTES:
        return TransformedRequest(
            raw,
            {"changed": False, "reason": "request exceeds transform limit"},
        )
    if "json" not in content_type.lower():
        return TransformedRequest(
            raw,
            {"changed": False, "reason": "non-json request"},
        )
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return TransformedRequest(
            raw,
            {"changed": False, "reason": "invalid json"},
        )
    if not isinstance(body, dict):
        return TransformedRequest(
            raw,
            {"changed": False, "reason": "json body is not an object"},
        )

    result: ProviderTransformResult = transform_provider_request(
        config.root,
        config.provider,
        body,
        request_path=request_path,
        compress_schemas=config.compress_schemas,
        compress_tool_results=config.compress_tool_results,
        deduplicate_history=config.deduplicate_history,
        tool_result_min_tokens=config.tool_result_min_tokens,
        prefix_tracking=config.prefix_tracking,
        model_routing_mode=config.model_routing_mode,
        model_routing_calibration_file=config.model_routing_calibration_file,
        model_routing_min_savings=config.model_routing_min_savings,
        context_budget_total_tokens=config.context_budget_total_tokens,
        provider_cache_mode=config.provider_cache_mode,
        provider_cache_expected_reuses=config.provider_cache_expected_reuses,
    )
    encoded = (
        json.dumps(
            result.body,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        if result.changed
        else raw
    )
    return TransformedRequest(encoded, result.metadata())


def _upstream_url(base: str, path: str) -> str:
    """Join only the incoming path/query to the configured upstream origin."""
    parsed = urlsplit(path)
    relative = parsed.path.lstrip("/")
    if parsed.query:
        relative += "?" + parsed.query
    normalized = base.rstrip("/") + "/"
    return urljoin(normalized, relative)


class _NoRedirect(HTTPRedirectHandler):
    """Return redirects to the client instead of forwarding credentials elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Disable urllib's automatic cross-origin redirect following."""
        del req, fp, code, msg, headers, newurl
        return None


def _open_upstream(request: Request, timeout: float):
    """Open one upstream request without following provider redirects."""
    return build_opener(_NoRedirect).open(request, timeout=timeout)


def _handler_factory(
    config: ProviderProxyConfig,
    *,
    opener: Callable = _open_upstream,
):
    """Build a request handler bound to one immutable proxy configuration."""

    class Handler(BaseHTTPRequestHandler):
        """Forward one client connection through the fixed proxy configuration."""

        server_version = "AccoProviderProxy/2"

        def log_message(self, format: str, *args) -> None:
            """Keep access logs terse and free of headers/request content."""
            print(
                f"acco proxy: {self.address_string()} "
                + format % args,
                file=sys.stderr,
            )

        def _health(self) -> None:
            """Return content-free local identity for persistent readiness checks."""
            payload = json.dumps(
                {
                    "ok": True,
                    "provider": config.provider,
                    "instance_id": config.instance_id,
                    "root_fingerprint": hashlib.sha256(
                        str(config.root.resolve()).encode()
                    ).hexdigest()[:16],
                },
                separators=(",", ":"),
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _dispatch(self) -> None:
            """Serve ACCO health locally or forward the provider request."""
            if self.command == "GET" and self.path == "/__acco/health":
                self._health()
                return
            self._proxy()

        def _proxy(self) -> None:
            """Transform one supported request and stream the upstream response."""
            length_header = self.headers.get("Content-Length")
            if self.command in {"POST", "PUT", "PATCH"} and length_header is None:
                self.send_error(411, "Content-Length required")
                return
            try:
                length = int(length_header or 0)
            except ValueError:
                self.send_error(400, "invalid Content-Length")
                return
            if length < 0 or length > _MAX_REQUEST_BYTES:
                self.send_error(413, "request body too large")
                return
            raw = self.rfile.read(length) if length else b""
            transformed = transform_request_bytes(
                config,
                raw,
                content_type=self.headers.get("Content-Type", ""),
                request_path=self.path,
            ) if raw else TransformedRequest(raw, {"changed": False})

            target = _upstream_url(config.upstream, self.path)
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in _HOP_BY_HOP
                and key.lower() not in {"host", "content-length"}
            }
            if transformed.body:
                headers["Content-Length"] = str(len(transformed.body))
            request = Request(
                target,
                data=transformed.body if raw else None,
                headers=headers,
                method=self.command,
            )
            try:
                response = opener(request, timeout=config.timeout_seconds)
            except HTTPError as exc:
                response = exc
            except OSError as exc:
                self.send_error(502, f"upstream unavailable: {exc}")
                return

            self.send_response(response.status)
            for key, value in response.headers.items():
                lowered = key.lower()
                if lowered in _HOP_BY_HOP or lowered == "content-length":
                    continue
                self.send_header(key, value)
            self.end_headers()

            request_meta = transformed.metadata.get("request", {})
            provider = (
                str(request_meta.get("provider") or config.provider)
                if isinstance(request_meta, dict)
                else config.provider
            )
            request_shape = (
                str(request_meta.get("shape") or "unknown")
                if isinstance(request_meta, dict)
                else "unknown"
            )
            streaming = bool(
                request_meta.get("streaming")
                if isinstance(request_meta, dict)
                else False
            )
            observer = (
                ProviderUsageObserver(
                    config.root,
                    provider=provider,
                    request_shape=request_shape,
                    streaming=streaming,
                    content_type=response.headers.get("Content-Type", ""),
                )
                if config.usage_telemetry
                else None
            )
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                if observer is not None:
                    observer.feed(chunk)
            response.close()
            if observer is not None:
                try:
                    observer.finish()
                except OSError as exc:
                    print(
                        "acco proxy usage telemetry unavailable: "
                        f"{type(exc).__name__}",
                        file=sys.stderr,
                    )

            meta = transformed.metadata
            if meta.get("changed"):
                routing = meta.get("model_routing") or {}
                route_text = (
                    f"; model={routing.get('from_model')}->{routing.get('to_model')}"
                    if routing.get("applied")
                    else ""
                )
                print(
                    "acco proxy transform: "
                    f"{meta.get('original_tokens', 0)} -> "
                    f"{meta.get('output_tokens', 0)} estimated tokens; "
                    f"dedup={meta.get('deduplicated_segments', 0)}; "
                    f"recoveries={len(meta.get('recovery_handles', []))}"
                    f"{route_text}",
                    file=sys.stderr,
                )

        do_POST = _dispatch
        do_PUT = _dispatch
        do_PATCH = _dispatch
        do_GET = _dispatch
        do_DELETE = _dispatch
        do_OPTIONS = _dispatch
        do_HEAD = _dispatch

    return Handler


def run_provider_proxy(config: ProviderProxyConfig) -> None:
    """Run the local provider proxy until interrupted."""
    config = config.validate()
    server = ThreadingHTTPServer(
        (config.bind, config.port),
        _handler_factory(config),
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
