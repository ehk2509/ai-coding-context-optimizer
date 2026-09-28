"""Deterministic adaptive disclosure for the MCP tool surface."""

from __future__ import annotations

import re
from collections.abc import Iterable

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")

ADAPTIVE_CORE = (
    "discover_tools",
    "build_context",
    "find_symbol",
    "browse_context",
    "memory_index",
    "recover_context",
    "route_task",
)

TOOL_GROUPS = {
    "memory": (
        "memory_index",
        "memory_search",
        "memory_get",
        "remember_memory",
        "recall_findings",
        "remember_finding",
        "knowledge_status",
    ),
    "recovery": (
        "recover_context",
        "recovery_status",
        "prefix_status",
    ),
    "retrieval": (
        "explain_ranking",
        "analyze_change_impact",
        "report_context_feedback",
        "index_status",
        "refresh_index",
        "semantic_index_status",
        "refresh_semantic_index",
    ),
    "review": (
        "review_diff",
        "build_diff_context",
        "analyze_change_impact",
    ),
    "output": (
        "output_policy",
        "compact_output",
    ),
    "routing": (
        "route_task",
    ),
    "execution": (
        "execute",
    ),
}

_GROUP_TERMS = {
    "memory": {
        "memory", "remember", "recall", "previous", "prior", "decision",
        "convention", "guardrail", "architecture", "bugfix", "history",
        "session", "knowledge",
    },
    "recovery": {
        "recover", "recovery", "original", "exact", "bytes", "tsr",
        "prefix", "cache",
    },
    "retrieval": {
        "search", "find", "where", "symbol", "context", "semantic", "index",
        "ranking", "retrieve", "retrieval", "dependency", "dependent", "caller",
        "impact",
    },
    "review": {
        "diff", "patch", "review", "change", "changed", "regression", "test",
        "tests", "api", "breaking", "staged",
    },
    "output": {
        "output", "response", "answer", "prose", "terse", "compact",
        "compress", "compression", "budget",
    },
    "routing": {
        "model", "route", "routing", "cost", "price", "pricing", "haiku",
        "sonnet", "opus",
    },
    "execution": {
        "analyze", "analysis", "aggregate", "batch", "count", "csv", "data",
        "execute", "execution", "json", "logs", "many", "statistics", "summarize",
        "scan",
    },
}


def _tokens(value: str) -> set[str]:
    """Return normalized task terms for deterministic tool-group routing."""
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(value)}


def adaptive_tool_names(
    query: str,
    available_names: Iterable[str],
    *,
    max_tools: int = 12,
) -> tuple[str, ...]:
    """Choose a bounded MCP surface from task vocabulary and stable groups."""
    if max_tools < len(ADAPTIVE_CORE):
        raise ValueError(
            f"adaptive MCP max_tools must be at least {len(ADAPTIVE_CORE)}"
        )
    available = tuple(available_names)
    available_set = set(available)
    selected = [name for name in ADAPTIVE_CORE if name in available_set]
    query_terms = _tokens(query)

    ranked_groups: list[tuple[int, str]] = []
    for group, trigger_terms in _GROUP_TERMS.items():
        matches = len(query_terms & trigger_terms)
        if matches:
            ranked_groups.append((matches, group))
    ranked_groups.sort(key=lambda item: (-item[0], item[1]))

    # Ordinary coding tasks need retrieval/review capability even when their
    # wording contains no routing vocabulary.
    if not ranked_groups:
        ranked_groups = [(1, "retrieval")]

    for _, group in ranked_groups:
        for name in TOOL_GROUPS[group]:
            if name in available_set and name not in selected:
                selected.append(name)
                if len(selected) >= max_tools:
                    return tuple(selected)

    return tuple(selected)


def adaptive_surface_description(query: str, names: tuple[str, ...]) -> dict:
    """Return explainable metadata for one adaptive tool selection."""
    return {
        "query": query,
        "profile": "adaptive",
        "tool_count": len(names),
        "tools": list(names),
        "policy": "deterministic-keyword-groups",
    }
