"""Optional structured-data middleware for RAG, API, and database contexts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
import re
from typing import Any

from .context_router import compact_json_value
from .estimate import estimate_tokens
from .recovery import RecoveryCapacityError, RecoveryStore

_TERM = re.compile(r"[A-Za-z0-9_./:@-]{2,}")


def _validate_json_value(value: Any, *, path: str = "$") -> None:
    """Require a strict JSON-compatible value without implicit Python coercions."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string object key")
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise ValueError(
        f"{path} contains unsupported {type(value).__name__}; "
        "middleware inputs must be strict JSON values"
    )


def _canonical_json(value: Any) -> str:
    """Serialize one validated value deterministically for tokens and recovery."""
    _validate_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def _terms(query: str) -> tuple[str, ...]:
    """Return stable lowercase focus terms for domain-level selection."""
    return tuple(dict.fromkeys(match.group(0).lower() for match in _TERM.finditer(query)))


def _score_item(item: Any, query_terms: tuple[str, ...]) -> int:
    """Return a simple deterministic lexical focus score for one JSON value."""
    if not query_terms:
        return 0
    rendered = _canonical_json(item).lower()
    return sum(rendered.count(term) for term in query_terms)


def _numeric_score(item: Any) -> float:
    """Read a conventional retrieval score without inventing one."""
    if not isinstance(item, dict):
        return float("-inf")
    for key in ("score", "relevance_score", "similarity"):
        value = item.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric = float(value)
            if math.isfinite(numeric):
                return numeric
    return float("-inf")


def _select_items(
    items: list[Any],
    *,
    query: str,
    limit: int,
    prefer_numeric_score: bool,
) -> tuple[list[Any], list[int]]:
    """Select bounded focused items while preserving their original ordering."""
    if limit <= 0:
        raise ValueError("item limit must be positive")
    if len(items) <= limit:
        return list(items), list(range(len(items)))

    query_terms = _terms(query)
    ranked: list[tuple[int, int, float, int]] = []
    for index, item in enumerate(items):
        lexical = _score_item(item, query_terms)
        numeric = _numeric_score(item) if prefer_numeric_score else float("-inf")
        ranked.append(
            (
                1 if lexical > 0 else 0,
                lexical,
                numeric,
                -index,
            )
        )

    if query_terms or (prefer_numeric_score and any(math.isfinite(row[2]) for row in ranked)):
        indexes = sorted(
            sorted(
                range(len(items)),
                key=lambda index: ranked[index],
                reverse=True,
            )[:limit]
        )
    else:
        indexes = list(range(limit))
    return [items[index] for index in indexes], indexes


def _result(
    *,
    domain: str,
    original: Any,
    candidate: Any,
    recovery: RecoveryStore,
    min_reduction: float,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Apply token/byte gates and exact canonical-JSON recovery to one candidate."""
    if not 0 <= min_reduction < 1:
        raise ValueError("min_reduction must be in [0, 1)")
    original_text = _canonical_json(original)
    candidate_text = _canonical_json(candidate)
    original_tokens = estimate_tokens(original_text)
    candidate_tokens = estimate_tokens(candidate_text)
    reduction = (
        0.0
        if not original_tokens
        else 1.0 - candidate_tokens / original_tokens
    )
    changed = (
        candidate != original
        and len(candidate_text.encode("utf-8")) < len(original_text.encode("utf-8"))
        and candidate_tokens < original_tokens
        and reduction >= min_reduction
    )
    handle = None
    value = original
    output_tokens = original_tokens
    if changed:
        try:
            handle = recovery.put(
                original_text,
                content_type="application/json",
                metadata={
                    "transform": "sdk-domain-middleware",
                    "domain": domain,
                    "representation": "canonical-json",
                    **metadata,
                },
            )
        except RecoveryCapacityError:
            changed = False
        else:
            value = candidate
            output_tokens = candidate_tokens

    return {
        "schema": 1,
        "domain": domain,
        "format": "json",
        "value": value,
        "changed": changed,
        "original_tokens": original_tokens,
        "output_tokens": output_tokens,
        "recovery_handle": handle,
        "metadata": {
            **metadata,
            "recovery_representation": "canonical-json",
        },
    }


def optimize_rag_context(
    documents: list[Any],
    *,
    query: str,
    recovery: RecoveryStore,
    max_documents: int = 8,
    min_reduction: float = 0.08,
) -> dict[str, Any]:
    """Compress caller-supplied RAG documents without performing retrieval."""
    if not isinstance(documents, list):
        raise ValueError("documents must be a JSON array")
    _validate_json_value(documents, path="documents")
    selected, indexes = _select_items(
        documents,
        query=query,
        limit=max_documents,
        prefer_numeric_score=True,
    )
    candidate = [
        compact_json_value(document, query=query)
        for document in selected
    ]
    return _result(
        domain="rag",
        original=documents,
        candidate=candidate,
        recovery=recovery,
        min_reduction=min_reduction,
        metadata={
            "documents": len(documents),
            "shown_documents": len(candidate),
            "omitted_documents": len(documents) - len(candidate),
            "selected_indexes": indexes,
            "selection": "query+declared-score" if query else "declared-score+order",
        },
    )


def optimize_api_payload(
    payload: Any,
    *,
    query: str,
    recovery: RecoveryStore,
    min_reduction: float = 0.08,
) -> dict[str, Any]:
    """Compress a caller-supplied JSON API payload for model context."""
    if not isinstance(payload, (dict, list)):
        raise ValueError("API payload must be a JSON object or array")
    _validate_json_value(payload, path="payload")
    candidate = compact_json_value(payload, query=query)
    return _result(
        domain="api",
        original=payload,
        candidate=candidate,
        recovery=recovery,
        min_reduction=min_reduction,
        metadata={
            "root_type": "object" if isinstance(payload, dict) else "array",
            "items": len(payload),
        },
    )


def _normalize_database_rows(
    rows: list[Any],
    columns: list[str] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize JSON row objects or positional rows into named row objects."""
    if not isinstance(rows, list):
        raise ValueError("rows must be a JSON array")
    if columns is not None:
        if (
            not isinstance(columns, list)
            or not columns
            or any(not isinstance(column, str) or not column for column in columns)
        ):
            raise ValueError("columns must be a nonempty array of strings")
        if len(set(columns)) != len(columns):
            raise ValueError("columns must not contain duplicates")

    normalized: list[dict[str, Any]] = []
    inferred_columns: list[str] = list(columns or [])
    for index, row in enumerate(rows):
        if isinstance(row, dict):
            _validate_json_value(row, path=f"rows[{index}]")
            if columns is not None:
                normalized.append(
                    {column: row.get(column) for column in columns}
                )
            else:
                normalized.append(dict(row))
                for key in row:
                    if key not in inferred_columns:
                        inferred_columns.append(key)
            continue
        if isinstance(row, list):
            if columns is None:
                raise ValueError(
                    "columns are required when database rows are positional arrays"
                )
            if len(row) != len(columns):
                raise ValueError(
                    f"rows[{index}] has {len(row)} values for {len(columns)} columns"
                )
            _validate_json_value(row, path=f"rows[{index}]")
            normalized.append(dict(zip(columns, row, strict=True)))
            continue
        raise ValueError(
            f"rows[{index}] must be a JSON object or positional array"
        )
    return normalized, inferred_columns


def optimize_database_rows(
    rows: list[Any],
    *,
    query: str,
    recovery: RecoveryStore,
    columns: list[str] | None = None,
    max_rows: int = 20,
    min_reduction: float = 0.08,
) -> dict[str, Any]:
    """Compress caller-supplied query results without connecting to a database."""
    normalized, resolved_columns = _normalize_database_rows(rows, columns)
    selected, indexes = _select_items(
        normalized,
        query=query,
        limit=max_rows,
        prefer_numeric_score=False,
    )
    candidate_rows = [
        compact_json_value(row, query=query)
        for row in selected
    ]
    original = {
        "columns": resolved_columns,
        "rows": normalized,
    }
    candidate = {
        "columns": resolved_columns,
        "rows": candidate_rows,
    }
    return _result(
        domain="database",
        original=original,
        candidate=candidate,
        recovery=recovery,
        min_reduction=min_reduction,
        metadata={
            "rows": len(normalized),
            "shown_rows": len(candidate_rows),
            "omitted_rows": len(normalized) - len(candidate_rows),
            "columns": len(resolved_columns),
            "selected_indexes": indexes,
        },
    )
