"""Universal recoverable context routing for large tool and provider payloads."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import StringIO
import json
import re
from typing import Any

from .browser_context import compress_browser_payload, detect_browser_payload_kind
from .estimate import estimate_tokens
from .output.pipeline import process_output
from .recovery import RecoveryCapacityError, RecoveryStore
from .tool_field_learning import important_field_names, observe_tool_json

_WORD = re.compile(r"[A-Za-z0-9_./:@-]{2,}")
_LOG_HINT = re.compile(
    r"(?im)(?:^|\s)(?:DEBUG|INFO|WARN|WARNING|ERROR|FATAL|TRACE)[:\s]|"
    r"Traceback \(most recent call last\)|\bat \S+[:(]\d+"
)
_HTML_HINT = re.compile(r"<(?:html|body|div|table|form|button|a|input)\b", re.I)
_SEARCH_HINT = re.compile(r"(?m)^(?:[^\n:]+:\d+(?::\d+)?:|https?://\S+)")
_CRITICAL = re.compile(r"(?i)(error|exception|fail|fatal|panic|traceback|assert|caused by)")


@dataclass(frozen=True)
class ContextRouteResult:
    """Describe one universal context transformation."""

    text: str
    kind: str
    changed: bool
    original_tokens: int
    output_tokens: int
    recovery_handle: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe routing result."""
        return {
            "text": self.text,
            "kind": self.kind,
            "changed": self.changed,
            "original_tokens": self.original_tokens,
            "output_tokens": self.output_tokens,
            "recovery_handle": self.recovery_handle,
            "metadata": self.metadata,
        }


def _terms(value: str) -> set[str]:
    """Return bounded lowercase focus terms."""
    return {match.group(0).lower() for match in _WORD.finditer(value)}


def detect_context_kind(text: str) -> str:
    """Classify a payload using deterministic syntax/content signals."""
    stripped = text.lstrip()
    if not stripped:
        return "plain"
    browser_kind = detect_browser_payload_kind(text)
    if browser_kind == "html":
        return "html"
    if browser_kind == "ax":
        return "browser-ax"
    if browser_kind == "json":
        return "browser-json"
    if stripped[:1] in "[{":
        try:
            json.loads(stripped)
            return "json"
        except (ValueError, TypeError):
            pass
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) >= 4:
        first = lines[0]
        for delimiter in (",", "\t", "|"):
            if delimiter in first:
                widths = [len(line.split(delimiter)) for line in lines[:8]]
                if min(widths, default=0) >= 2 and max(widths) == min(widths):
                    return "table"
    if _LOG_HINT.search(text):
        return "log"
    if len(lines) >= 4 and sum(bool(_SEARCH_HINT.search(line)) for line in lines[:30]) >= 3:
        return "search-results"
    return "plain"


def _contains_terms(value: Any, query_terms: set[str]) -> bool:
    """Return whether serialized value contains at least one focus term."""
    if not query_terms:
        return False
    rendered = json.dumps(value, ensure_ascii=False).lower()
    return any(term in rendered for term in query_terms)


def _compact_json_value(
    value: Any,
    query_terms: set[str],
    depth: int = 0,
    important_fields: set[str] | None = None,
) -> Any:
    """Compact large JSON containers while retaining schema and focused samples."""
    important = important_fields or set()
    if depth >= 4:
        if isinstance(value, dict):
            learned = {
                str(key): item
                for key, item in value.items()
                if str(key) in important
            }
            if learned:
                return {
                    "_acco": {
                        "type": "dict",
                        "items": len(value),
                        "learned_fields": len(learned),
                    },
                    **learned,
                }
            return {"_acco": {"type": "dict", "items": len(value)}}
        if isinstance(value, list):
            return {"_acco": {"type": "list", "items": len(value)}}
        return value
    if isinstance(value, dict):
        return {
            str(key): _compact_json_value(item, query_terms, depth + 1, important)
            for key, item in value.items()
        }
    if isinstance(value, list):
        if len(value) <= 10:
            return [_compact_json_value(item, query_terms, depth + 1) for item in value]
        learned = [
            item
            for item in value
            if isinstance(item, dict)
            and any(
                str(key) in important
                and item.get(key) not in (None, "", False, [], {})
                for key in item
            )
        ][:4]
        focused = [item for item in value if _contains_terms(item, query_terms)][:6]
        samples: list[Any] = []
        for item in [*learned, *focused, *value[:3]]:
            if not any(item == existing for existing in samples):
                samples.append(item)
            if len(samples) >= 6:
                break
        if not learned and not focused and len(value) > 3 and len(samples) < 6:
            samples.append(value[-1])
        return {
            "_acco": {
                "type": "list",
                "items": len(value),
                "shown": len(samples),
                "focused": bool(focused),
            },
            "items": [
                _compact_json_value(item, query_terms, depth + 1, important)
                for item in samples
            ],
        }
    return value


def compact_json_value(
    value: Any,
    *,
    query: str = "",
    important_fields: set[str] | None = None,
) -> Any:
    """Return ACCO's deterministic structural JSON compaction for SDK middleware.

    The returned value is JSON-compatible when the input is JSON-compatible.
    This helper performs no persistence by itself; callers that accept a lossy
    result must apply ACCO's normal exact-recovery gate.
    """
    return _compact_json_value(value, _terms(query), important_fields=important_fields)


def _compress_json(
    text: str,
    query: str,
    *,
    important_fields: set[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return a compact structural JSON representation."""
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return text, {}
    compact = compact_json_value(value, query=query, important_fields=important_fields)
    candidate = json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n"
    return candidate, {"json_root": type(value).__name__}


def _compress_log(text: str, query: str, max_lines: int) -> tuple[str, dict[str, Any]]:
    """Retain log diagnostics, query matches, and bounded head/tail context."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text, {}
    query_terms = _terms(query)
    selected: set[int] = set(range(min(12, len(lines))))
    selected.update(range(max(0, len(lines) - 12), len(lines)))
    critical = 0
    focused = 0
    for index, line in enumerate(lines):
        lowered = line.lower()
        if _CRITICAL.search(line):
            selected.add(index)
            critical += 1
        elif query_terms and any(term in lowered for term in query_terms):
            selected.add(index)
            focused += 1
        if len(selected) >= max_lines:
            break
    ordered = sorted(selected)[:max_lines]
    body = [
        f"[acco log: {len(lines)} lines -> {len(ordered)} retained]",
        *(lines[index] for index in ordered),
    ]
    return "\n".join(body) + "\n", {
        "critical_lines": critical,
        "focused_lines": focused,
    }


def _table_delimiter(text: str) -> str | None:
    """Return a stable delimiter for a simple rectangular text table."""
    first = next((line for line in text.splitlines() if line.strip()), "")
    for delimiter in ("\t", ",", "|"):
        if delimiter in first:
            return delimiter
    return None


def _compress_table(text: str, query: str, max_lines: int) -> tuple[str, dict[str, Any]]:
    """Keep a table header plus focused/sample rows using the original delimiter."""
    delimiter = _table_delimiter(text)
    if delimiter is None:
        return text, {}
    try:
        rows = list(csv.reader(StringIO(text), delimiter=delimiter))
    except csv.Error:
        return text, {}
    if len(rows) <= max_lines or not rows:
        return text, {}
    query_terms = _terms(query)
    header = rows[0]
    focused = [
        row for row in rows[1:]
        if query_terms and any(term in " ".join(row).lower() for term in query_terms)
    ][: max(0, max_lines - 2)]
    remaining = max(0, max_lines - 1 - len(focused))
    samples = focused + rows[1 : 1 + remaining]
    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in samples:
        key = tuple(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    output = StringIO()
    writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(unique)
    output.write(f"[acco table: {len(rows) - 1} rows -> {len(unique)} shown]\n")
    return output.getvalue(), {"rows": len(rows) - 1, "shown": len(unique)}


def _compress_search_results(text: str, query: str, max_lines: int) -> tuple[str, dict[str, Any]]:
    """Deduplicate search-result lines and prioritize exact query matches."""
    lines = [line for line in text.splitlines() if line.strip()]
    query_terms = _terms(query)
    unique = list(dict.fromkeys(lines))
    focused = [
        line for line in unique
        if query_terms and any(term in line.lower() for term in query_terms)
    ]
    remainder = [line for line in unique if line not in set(focused)]
    kept = (focused + remainder)[:max_lines]
    if len(kept) >= len(lines):
        return text, {}
    body = [
        f"[acco search results: {len(lines)} lines -> {len(kept)} retained]",
        *kept,
    ]
    return "\n".join(body) + "\n", {
        "results": len(lines),
        "unique": len(unique),
        "shown": len(kept),
    }


def _compress_plain(text: str, command: str, max_lines: int) -> tuple[str, dict[str, Any]]:
    """Use the existing failure-aware output pipeline for arbitrary text."""
    result = process_output(
        text,
        command or "context-router",
        max_lines=max_lines,
        keep_tail=min(24, max(0, max_lines // 4)),
        min_reduction=0.02,
    )
    return result.text, {
        "processor": result.processor,
        "failed": result.failed,
    }


def route_context(
    text: str,
    *,
    query: str = "",
    recovery: RecoveryStore,
    command: str = "",
    max_lines: int = 120,
    min_reduction: float = 0.08,
) -> ContextRouteResult:
    """Route a payload through its safest compact representation.

    Every lossy transform is accepted only after exact bytes are durably stored.
    If recovery capacity is unavailable or the replacement is not materially
    smaller, the original payload is returned unchanged.
    """
    if max_lines <= 0:
        raise ValueError("context router max_lines must be positive")
    if not 0 <= min_reduction < 1:
        raise ValueError("context router min_reduction must be in [0, 1)")
    original_tokens = estimate_tokens(text)
    kind = detect_context_kind(text)
    if not text:
        return ContextRouteResult(text, kind, False, 0, 0, None, {})

    if kind in {"html", "browser-ax", "browser-json"}:
        format_hint = {
            "html": "html",
            "browser-ax": "ax",
            "browser-json": "json",
        }[kind]
        browser = compress_browser_payload(
            text,
            query=query,
            max_lines=max_lines,
            recovery=recovery,
            format_hint=format_hint,
        )
        return ContextRouteResult(
            browser.text,
            kind,
            browser.changed,
            browser.original_tokens,
            browser.output_tokens,
            browser.recovery_handle,
            {
                "matched_terms": list(browser.matched_terms),
                "browser_kind": browser.kind,
                "source_items": browser.source_items,
                "shown_items": browser.shown_items,
                "interactive_items": browser.interactive_items,
            },
        )
    if kind == "json":
        candidate, metadata = _compress_json(text, query)
    elif kind == "table":
        candidate, metadata = _compress_table(text, query, max_lines)
    elif kind == "log":
        candidate, metadata = _compress_log(text, query, max_lines)
    elif kind == "search-results":
        candidate, metadata = _compress_search_results(text, query, max_lines)
    else:
        candidate, metadata = _compress_plain(text, command, max_lines)

    candidate_tokens = estimate_tokens(candidate)
    reduction = (
        0.0 if not original_tokens
        else 1.0 - candidate_tokens / original_tokens
    )
    if (
        candidate == text
        or len(candidate.encode()) >= len(text.encode())
        or candidate_tokens >= original_tokens
        or reduction < min_reduction
    ):
        return ContextRouteResult(
            text, kind, False, original_tokens, original_tokens, None, metadata
        )

    try:
        handle = recovery.put(
            text,
            content_type="application/json" if kind == "json" else "text/plain",
            metadata={"transform": "context-router", "kind": kind, **metadata},
        )
    except RecoveryCapacityError:
        return ContextRouteResult(
            text, kind, False, original_tokens, original_tokens, None, metadata
        )
    rendered = candidate.rstrip() + f"\n[acco recovery: {handle}]\n"
    output_tokens = estimate_tokens(rendered)
    if output_tokens >= original_tokens or len(rendered.encode()) >= len(text.encode()):
        return ContextRouteResult(
            text, kind, False, original_tokens, original_tokens, None, metadata
        )
    return ContextRouteResult(
        rendered, kind, True, original_tokens, output_tokens, handle, metadata
    )
