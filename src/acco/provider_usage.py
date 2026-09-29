"""Content-free provider response usage observation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .efficiency.store import append_event
from .provider_cache import observed_cache_evidence

_MAX_JSON_OBSERVE_BYTES = 2 * 1024 * 1024


def _int(value: object) -> int | None:
    """Return a nonnegative integer token counter when present."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def normalize_provider_usage(provider: str, payload: object) -> dict[str, Any]:
    """Extract comparable token counters from one provider response payload."""
    if not isinstance(payload, dict):
        return {}
    provider = provider.strip().lower()
    source = payload
    if provider == "anthropic" and isinstance(payload.get("message"), dict):
        source = payload["message"]
    elif provider == "openai" and isinstance(payload.get("response"), dict):
        source = payload["response"]
    usage: object = source.get("usage")
    if provider == "gemini":
        usage = payload.get("usageMetadata")
    if not isinstance(usage, dict):
        usage = {}

    result: dict[str, Any] = {}
    if provider == "anthropic":
        mapping = {
            "input_tokens": "input_tokens",
            "output_tokens": "output_tokens",
            "cache_creation_input_tokens": "cache_creation_input_tokens",
            "cache_read_input_tokens": "cache_read_input_tokens",
        }
        for target, source_key in mapping.items():
            value = _int(usage.get(source_key))
            if value is not None:
                result[target] = value
    elif provider == "openai":
        input_tokens = _int(usage.get("input_tokens"))
        if input_tokens is None:
            input_tokens = _int(usage.get("prompt_tokens"))
        output_tokens = _int(usage.get("output_tokens"))
        if output_tokens is None:
            output_tokens = _int(usage.get("completion_tokens"))
        total_tokens = _int(usage.get("total_tokens"))
        if input_tokens is not None:
            result["input_tokens"] = input_tokens
        if output_tokens is not None:
            result["output_tokens"] = output_tokens
        if total_tokens is not None:
            result["total_tokens"] = total_tokens
        details = usage.get("input_tokens_details")
        if not isinstance(details, dict):
            details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            cached = _int(details.get("cached_tokens"))
            if cached is not None:
                result["cache_read_input_tokens"] = cached
    elif provider == "gemini":
        mapping = {
            "input_tokens": "promptTokenCount",
            "output_tokens": "candidatesTokenCount",
            "cache_read_input_tokens": "cachedContentTokenCount",
            "total_tokens": "totalTokenCount",
        }
        for target, source_key in mapping.items():
            value = _int(usage.get(source_key))
            if value is not None:
                result[target] = value
    else:
        for target in ("input_tokens", "output_tokens", "total_tokens"):
            value = _int(usage.get(target))
            if value is not None:
                result[target] = value

    model = source.get("model")
    if not isinstance(model, str):
        model = payload.get("model")
    if not isinstance(model, str):
        model = payload.get("modelVersion")
    if isinstance(model, str) and model.strip():
        result["model"] = model.strip()[:160]
    return result


class ProviderUsageObserver:
    """Observe response bytes without altering them and persist only token metadata."""

    def __init__(
        self,
        root: Path,
        *,
        provider: str,
        request_shape: str,
        streaming: bool,
        content_type: str = "",
    ):
        """Create one bounded response observer."""
        self.root = root.resolve()
        self.provider = provider
        self.request_shape = request_shape
        self.streaming = streaming
        self.content_type = content_type.lower()
        self._json = bytearray()
        self._line = bytearray()
        self._usage: dict[str, Any] = {}

    def _merge(self, payload: object) -> None:
        """Merge cumulative provider counters while retaining the largest observed value."""
        current = normalize_provider_usage(self.provider, payload)
        for key, value in current.items():
            if key == "model":
                self._usage[key] = value
            elif isinstance(value, int):
                previous = self._usage.get(key)
                self._usage[key] = max(value, previous if isinstance(previous, int) else 0)

    def _consume_line(self, raw: bytes) -> None:
        """Parse one SSE data line when it contains JSON."""
        line = raw.strip()
        if not line.startswith(b"data:"):
            return
        data = line[5:].strip()
        if not data or data == b"[DONE]":
            return
        try:
            payload = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        self._merge(payload)

    def feed(self, chunk: bytes) -> None:
        """Observe one upstream response chunk without changing caller-visible bytes."""
        if not chunk:
            return
        if self.streaming or "event-stream" in self.content_type:
            self._line.extend(chunk)
            while b"\n" in self._line:
                line, _, rest = self._line.partition(b"\n")
                self._line = bytearray(rest)
                self._consume_line(bytes(line))
            return
        if len(self._json) < _MAX_JSON_OBSERVE_BYTES:
            remaining = _MAX_JSON_OBSERVE_BYTES - len(self._json)
            self._json.extend(chunk[:remaining])

    def finish(self) -> dict[str, Any]:
        """Finalize usage extraction and append one content-free evidence event."""
        if self._line:
            self._consume_line(bytes(self._line))
            self._line.clear()
        if self._json:
            try:
                payload = json.loads(bytes(self._json))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, list):
                for item in payload:
                    self._merge(item)
            else:
                self._merge(payload)
        if not self._usage:
            return {}
        cache_evidence = observed_cache_evidence(self.provider, self._usage)
        event = {
            "kind": "provider_usage",
            "feature": "provider_boundary",
            "provider": self.provider,
            "request_shape": self.request_shape,
            "streaming": self.streaming,
            **self._usage,
            "cache_observed": cache_evidence["cache_observed"],
            "cache_evidence_basis": cache_evidence["evidence_basis"],
        }
        append_event(self.root, event)
        return event
