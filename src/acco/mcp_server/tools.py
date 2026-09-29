"""Application-level MCP tool registry and tool implementations."""

from __future__ import annotations

from collections.abc import Iterable
import base64
from pathlib import Path

from ..efficiency.ledger import recent_ledger_events, search_ledger
from ..execution import ExecutionLimits, batch_execute, execute_file, execute_program
from ..output_saver import build_output_policy, compact_output
from ..model_routing import (
    DEFAULT_ALLOWED_MODELS,
    DEFAULT_ROUTING_CALIBRATION_FILE,
    load_routing_calibration,
    route_task,
)
from ..patch_context import build_diff_context, review_patch
from ..prefix_cache import prefix_status
from ..recovery import RecoveryStore
from .contracts import McpToolContext, McpToolSpec
from .tool_surface import ADAPTIVE_CORE, adaptive_surface_description, adaptive_tool_names


class McpToolRegistry:
    """Resolve MCP tool calls without coupling handlers to JSON-RPC transport."""

    def __init__(self, specs: Iterable[McpToolSpec]):
        """Build a registry and reject ambiguous duplicate tool names."""
        by_name: dict[str, McpToolSpec] = {}
        for spec in specs:
            if spec.name in by_name:
                raise ValueError(f"duplicate MCP tool registration: {spec.name}")
            by_name[spec.name] = spec
        self._specs = by_name

    def schemas(self) -> list[dict]:
        """Return tools/list schemas in deterministic registration order."""
        return [spec.to_schema() for spec in self._specs.values()]

    def names(self) -> tuple[str, ...]:
        """Return registered tool names in deterministic order."""
        return tuple(self._specs)

    def select(self, names: Iterable[str]) -> McpToolRegistry:
        """Return a registry containing only named tools in original order."""
        allowed = set(names)
        return McpToolRegistry(
            spec for name, spec in self._specs.items() if name in allowed
        )

    def call(self, name: str, context: McpToolContext, arguments: dict) -> object:
        """Call a registered application handler or reject an unknown tool."""
        spec = self._specs.get(name)
        if spec is None:
            raise ValueError(f"unknown tool: {name}")
        return spec.handler(context, arguments)


def _build_context(context: McpToolContext, arguments: dict) -> dict:
    """Build a task-aware source context pack."""
    semantic = bool(
        arguments.get("semantic", arguments.get("embeddings", False))
    )
    pack = context.repository.build_context(
        str(arguments.get("query", "")),
        max_tokens=int(arguments.get("max_tokens", 6000)),
        target_symbol=arguments.get("target_symbol"),
        embeddings=semantic,
    )
    return {
        "text": pack.text,
        "estimated_tokens": pack.estimated_tokens,
        "selected_files": pack.selected_files,
        "selected_symbols": pack.selected_symbols,
        "redactions": pack.redactions,
        "closure_files": pack.closure_files,
        "cache_hit": pack.cache_hit,
        "cache_key": pack.cache_key,
        "semantic_index": (
            context.repository.semantic_index_status() if semantic else None
        ),
    }


def _browse_context(context: McpToolContext, arguments: dict) -> dict:
    """Return ranked repository source candidates for a query."""
    return context.repository.browse(
        str(arguments.get("query", "")),
        max_files=int(arguments.get("max_files", 8)),
        preview_tokens=int(arguments.get("preview_tokens", 350)),
    )


def _explain_ranking(context: McpToolContext, arguments: dict) -> dict:
    """Explain stage-by-stage file-ranking score contributions."""
    return context.repository.explain_ranking(
        str(arguments.get("query", "")),
        max_files=int(arguments.get("max_files", 8)),
        changed_boost=bool(arguments.get("changed_boost", True)),
        embeddings=bool(arguments.get("embeddings", False)),
    )


def _find_symbol(context: McpToolContext, arguments: dict) -> list[dict]:
    """Find symbol definitions and source ranges."""
    return context.repository.find_symbols(str(arguments.get("name", "")))


def _analyze_change_impact(context: McpToolContext, arguments: dict) -> dict:
    """Return callers, dependents, tests, and graph evidence for a target."""
    return context.repository.impact(
        str(arguments.get("target", ""))
    ).to_dict()


def _report_context_feedback(context: McpToolContext, arguments: dict) -> dict:
    """Record whether one included file was useful for future local ranking."""
    scores = context.repository.feedback(
        str(arguments.get("path", "")),
        useful=bool(arguments.get("useful")),
    )
    return {"scores": scores}


def _index_status(context: McpToolContext, arguments: dict) -> dict:
    """Return persistent repository-index lifecycle metadata."""
    del arguments
    return context.repository.status()


def _refresh_index(context: McpToolContext, arguments: dict) -> dict:
    """Refresh the repository index and return its resulting status."""
    del arguments
    context.repository.refresh()
    return context.repository.status()


def _semantic_index_status(context: McpToolContext, arguments: dict) -> dict:
    """Return semantic-vector index status without loading the embedding model."""
    del arguments
    return context.repository.semantic_index_status()


def _refresh_semantic_index(context: McpToolContext, arguments: dict) -> dict:
    """Build or incrementally refresh persistent local semantic vectors."""
    del arguments
    return context.repository.sync_semantic_index()


def _remember_finding(context: McpToolContext, arguments: dict) -> dict:
    """Persist one explicit evidence-backed project finding."""
    anchors = arguments.get("anchors")
    invalidators = arguments.get("invalidators")
    supersedes = arguments.get("supersedes")
    return context.repository.remember_finding(
        claim=str(arguments.get("claim", "")),
        anchors=[str(value) for value in anchors] if isinstance(anchors, list) else [],
        evidence=str(arguments.get("evidence", "")),
        applicability=str(arguments.get("applicability", "")),
        confidence=str(arguments.get("confidence", "verified")),
        invalidators=(
            [str(value) for value in invalidators]
            if isinstance(invalidators, list)
            else None
        ),
        supersedes=(
            [str(value) for value in supersedes]
            if isinstance(supersedes, list)
            else None
        ),
        source="mcp",
    )


def _recall_findings(context: McpToolContext, arguments: dict) -> list[dict]:
    """Recall current evidence-backed findings relevant to one query."""
    return context.repository.recall_findings(
        str(arguments.get("query", "")),
        limit=int(arguments.get("limit", 5)),
        include_stale=bool(arguments.get("include_stale", False)),
    )


def _knowledge_status(context: McpToolContext, arguments: dict) -> dict:
    """Return knowledge counts without exposing finding contents."""
    del arguments
    return context.repository.knowledge_status()


def _remember_memory(context: McpToolContext, arguments: dict) -> dict:
    """Persist typed project memory without storing raw conversation text."""
    anchors = arguments.get("anchors")
    tags = arguments.get("tags")
    invalidators = arguments.get("invalidators")
    related_ids = arguments.get("related_ids")
    return context.repository.remember_memory(
        claim=str(arguments.get("claim", "")),
        anchors=[str(value) for value in anchors] if isinstance(anchors, list) else [],
        evidence=str(arguments.get("evidence", "")),
        applicability=str(arguments.get("applicability", "")),
        kind=str(arguments.get("kind", "fact")),
        confidence=str(arguments.get("confidence", "verified")),
        tags=[str(value) for value in tags] if isinstance(tags, list) else None,
        importance=int(arguments.get("importance", 3)),
        invalidators=(
            [str(value) for value in invalidators]
            if isinstance(invalidators, list)
            else None
        ),
        related_ids=(
            [str(value) for value in related_ids]
            if isinstance(related_ids, list)
            else None
        ),
        source="mcp-memory",
        deduplicate=bool(arguments.get("deduplicate", True)),
    )


def _memory_index(context: McpToolContext, arguments: dict) -> list[dict]:
    """Return compact memory metadata as the cheapest discovery layer."""
    kind = arguments.get("kind")
    return context.repository.memory_index(
        str(arguments.get("query", "")),
        kind=str(kind) if kind else None,
        limit=int(arguments.get("limit", 20)),
        include_stale=bool(arguments.get("include_stale", False)),
    )


def _memory_search(context: McpToolContext, arguments: dict) -> list[dict]:
    """Return bounded memory snippets for relevance confirmation."""
    kind = arguments.get("kind")
    return context.repository.memory_search(
        str(arguments.get("query", "")),
        kind=str(kind) if kind else None,
        limit=int(arguments.get("limit", 10)),
        include_stale=bool(arguments.get("include_stale", False)),
    )


def _memory_get(context: McpToolContext, arguments: dict) -> list[dict]:
    """Return full memory records only after explicit id selection."""
    ids = arguments.get("ids")
    return context.repository.memory_get(
        [str(value) for value in ids] if isinstance(ids, list) else [],
        include_stale=bool(arguments.get("include_stale", True)),
    )


def _recover_context(context: McpToolContext, arguments: dict) -> dict:
    """Recover exact bytes or one selected typed-object subtree."""
    reference = str(arguments.get("handle", ""))
    pointer = arguments.get("pointer")
    store = RecoveryStore(context.root)
    if reference.startswith("tsr_obj_") or reference.startswith("tsr://"):
        selected = store.select(
            reference,
            str(pointer) if isinstance(pointer, str) else None,
        )
        return {"kind": "object", **selected}
    record = store.get(reference)
    try:
        text = record.payload.decode("utf-8")
        encoding = "utf-8"
        payload = text
    except UnicodeDecodeError:
        encoding = "base64"
        payload = base64.b64encode(record.payload).decode("ascii")
    return {
        "kind": "bytes",
        "handle": record.handle,
        "content_type": record.content_type,
        "encoding": encoding,
        "payload": payload,
        "size_bytes": record.size_bytes,
        "metadata": record.metadata,
        "access_count": record.access_count,
    }


def _recovery_status(context: McpToolContext, arguments: dict) -> dict:
    """Return exact-recovery capacity metadata without source bytes."""
    del arguments
    return RecoveryStore(context.root).stats()


def _prefix_status(context: McpToolContext, arguments: dict) -> dict:
    """Return stable-prefix reuse counters without provider request content."""
    del arguments
    return prefix_status(context.root)


def _discover_tools(context: McpToolContext, arguments: dict) -> dict:
    """Suggest and describe a bounded specialist MCP surface for one task."""
    del context
    query = str(arguments.get("query", ""))
    max_tools = int(arguments.get("max_tools", 12))
    names = adaptive_tool_names(
        query,
        DEFAULT_TOOL_REGISTRY.names(),
        max_tools=max_tools,
    )
    registry = DEFAULT_TOOL_REGISTRY.select(names)
    result = adaptive_surface_description(query, names)
    result["schemas"] = registry.schemas()
    result["refresh_tools_list"] = True
    return result


def _build_diff_context(context: McpToolContext, arguments: dict) -> dict:
    """Build context around the current Git patch and its impact closure."""
    return build_diff_context(
        context.root,
        base=str(arguments.get("base", "HEAD")),
        staged=bool(arguments.get("staged", False)),
        max_tokens=int(arguments.get("max_tokens", 6000)),
    )


def _review_diff(context: McpToolContext, arguments: dict) -> dict:
    """Report changed symbols, impact, API changes, and test coverage signals."""
    return review_patch(
        context.root,
        base=str(arguments.get("base", "HEAD")),
        staged=bool(arguments.get("staged", False)),
    )


def _route_task(context: McpToolContext, arguments: dict) -> dict:
    """Return one model-routing decision for a model-selectable orchestrator."""
    allowed = arguments.get("allowed_models")
    calibration_name = str(
        arguments.get("calibration_file") or DEFAULT_ROUTING_CALIBRATION_FILE
    )
    calibration_path = Path(calibration_name)
    if not calibration_path.is_absolute():
        calibration_path = context.root / calibration_path
    calibration = load_routing_calibration(calibration_path)
    return route_task(
        str(arguments.get("prompt", "")),
        input_tokens=(
            int(arguments["input_tokens"])
            if "input_tokens" in arguments
            else None
        ),
        output_tokens=(
            int(arguments["output_tokens"])
            if "output_tokens" in arguments
            else None
        ),
        current_model=(
            str(arguments["current_model"])
            if arguments.get("current_model")
            else None
        ),
        allowed_models=(
            [str(value) for value in allowed]
            if isinstance(allowed, list)
            else DEFAULT_ALLOWED_MODELS
        ),
        min_savings=float(arguments.get("min_savings", 0.05)),
        conservative=bool(arguments.get("conservative", True)),
        calibration=calibration,
    ).to_dict()



def _execute(context: McpToolContext, arguments: dict) -> dict:
    """Run restricted local analysis over explicit repository text files."""
    files = arguments.get("files")
    if not isinstance(files, list):
        raise ValueError("files must be an array of repository-relative paths")
    return execute_program(
        context.root,
        str(arguments.get("code", "")),
        [str(value) for value in files],
        recovery=RecoveryStore(context.root),
        limits=ExecutionLimits(
            timeout_seconds=int(arguments.get("timeout_seconds", 5)),
            max_result_bytes=int(arguments.get("max_result_bytes", 64 * 1024)),
        ),
    )


def _execute_file(context: McpToolContext, arguments: dict) -> dict:
    """Run a repository-contained restricted analysis program."""
    files = arguments.get("files")
    if not isinstance(files, list):
        raise ValueError("files must be an array of repository-relative paths")
    return execute_file(
        context.root,
        str(arguments.get("program_file", "")),
        [str(value) for value in files],
        recovery=RecoveryStore(context.root),
        limits=ExecutionLimits(
            timeout_seconds=int(arguments.get("timeout_seconds", 5)),
            max_result_bytes=int(arguments.get("max_result_bytes", 64 * 1024)),
        ),
    )


def _batch_execute(context: McpToolContext, arguments: dict) -> dict:
    """Run multiple restricted analysis jobs under one bounded batch."""
    jobs = arguments.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("jobs must be an array")
    return batch_execute(
        context.root,
        jobs,
        recovery=RecoveryStore(context.root),
        limits=ExecutionLimits(
            timeout_seconds=int(arguments.get("timeout_seconds", 5)),
            max_result_bytes=int(arguments.get("max_result_bytes", 64 * 1024)),
        ),
    )


def _session_search(context: McpToolContext, arguments: dict) -> dict:
    """Search persisted structured session history."""
    kinds = arguments.get("kinds")
    return search_ledger(
        context.root,
        str(arguments.get("query", "")),
        kinds=[str(value) for value in kinds] if isinstance(kinds, list) else None,
        session=str(arguments["session"]) if arguments.get("session") else None,
        limit=int(arguments.get("limit", 12)),
    )


def _session_recent(context: McpToolContext, arguments: dict) -> dict:
    """Return recent structured session events without transcript content."""
    kinds = arguments.get("kinds")
    events = recent_ledger_events(
        context.root,
        session=str(arguments["session"]) if arguments.get("session") else None,
        kinds=[str(value) for value in kinds] if isinstance(kinds, list) else None,
        limit=int(arguments.get("limit", 12)),
    )
    return {"schema": 1, "count": len(events), "events": events}


def _output_policy(context: McpToolContext, arguments: dict) -> dict:
    """Return generation-time response policy metadata."""
    del context
    policy = build_output_policy(
        str(arguments.get("mode", "normal")),
        int(arguments["max_tokens"]) if "max_tokens" in arguments else None,
        str(arguments.get("task", "general")),
    )
    return policy.to_dict()


def _compact_output(context: McpToolContext, arguments: dict) -> dict:
    """Compact generated prose while preserving fenced code and diffs."""
    del context
    result = compact_output(
        str(arguments.get("text", "")),
        mode=str(arguments.get("mode", "normal")),
        max_tokens=int(arguments["max_tokens"]) if "max_tokens" in arguments else None,
        enforce_budget=bool(arguments.get("enforce_budget", False)),
    )
    return result.to_dict()


DEFAULT_TOOL_REGISTRY = McpToolRegistry(
    [
        McpToolSpec(
            "build_context",
            "Build a task-aware source context pack under a hard token budget.",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "max_tokens": {"type": "integer", "minimum": 1},
                    "target_symbol": {"type": "string"},
                    "semantic": {"type": "boolean"},
                },
            },
            _build_context,
        ),
        McpToolSpec(
            "find_symbol",
            "Find exact or partial symbol definitions with source ranges.",
            {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
            _find_symbol,
        ),
        McpToolSpec(
            "browse_context",
            "Inspect ranked files, selected symbols, fuzzy corrections, and source previews.",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "max_files": {"type": "integer", "minimum": 1},
                    "preview_tokens": {"type": "integer", "minimum": 1},
                },
            },
            _browse_context,
        ),
        McpToolSpec(
            "explain_ranking",
            "Explain stage-by-stage score contributions for ranked repository files.",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "max_files": {"type": "integer", "minimum": 1},
                    "changed_boost": {"type": "boolean"},
                    "embeddings": {"type": "boolean"},
                },
            },
            _explain_ranking,
        ),
        McpToolSpec(
            "analyze_change_impact",
            "Find callers, dependents, and related tests for a file or symbol.",
            {
                "type": "object",
                "required": ["target"],
                "properties": {"target": {"type": "string"}},
            },
            _analyze_change_impact,
        ),
        McpToolSpec(
            "report_context_feedback",
            "Record whether an included file was useful for future local ranking.",
            {
                "type": "object",
                "required": ["path", "useful"],
                "properties": {
                    "path": {"type": "string"},
                    "useful": {"type": "boolean"},
                },
            },
            _report_context_feedback,
        ),
        McpToolSpec(
            "index_status",
            "Report persistent repository index size, reuse, and refresh time.",
            {"type": "object", "properties": {}},
            _index_status,
        ),
        McpToolSpec(
            "refresh_index",
            "Incrementally refresh the persistent repository index.",
            {"type": "object", "properties": {}},
            _refresh_index,
        ),
        McpToolSpec(
            "semantic_index_status",
            "Report persistent chunk-vector index state without loading the embedding model.",
            {"type": "object", "properties": {}},
            _semantic_index_status,
        ),
        McpToolSpec(
            "refresh_semantic_index",
            "Build or incrementally refresh persistent local chunk embeddings.",
            {"type": "object", "properties": {}},
            _refresh_semantic_index,
        ),
        McpToolSpec(
            "remember_finding",
            "Persist a durable evidence-backed project finding anchored to current source files.",
            {
                "type": "object",
                "required": ["claim", "anchors", "evidence", "applicability"],
                "properties": {
                    "claim": {"type": "string"},
                    "anchors": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {"type": "string"},
                    },
                    "evidence": {"type": "string"},
                    "applicability": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["speculative", "probable", "verified"],
                    },
                    "invalidators": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "supersedes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            _remember_finding,
        ),
        McpToolSpec(
            "recall_findings",
            "Recall durable project findings; changed source anchors are excluded as stale by default.",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    "include_stale": {"type": "boolean"},
                },
            },
            _recall_findings,
        ),
        McpToolSpec(
            "knowledge_status",
            "Report active, stale, and superseded project-knowledge counts.",
            {"type": "object", "properties": {}},
            _knowledge_status,
        ),
        McpToolSpec(
            "remember_memory",
            "Persist typed project memory with source anchors, importance, tags, and deduplication.",
            {
                "type": "object",
                "required": ["claim", "anchors", "evidence", "applicability", "kind"],
                "properties": {
                    "claim": {"type": "string"},
                    "anchors": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {"type": "string"},
                    },
                    "evidence": {"type": "string"},
                    "applicability": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "decision",
                            "bugfix",
                            "convention",
                            "guardrail",
                            "architecture",
                            "fact",
                            "finding",
                        ],
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["speculative", "probable", "verified"],
                    },
                    "tags": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {"type": "string"},
                    },
                    "importance": {"type": "integer", "minimum": 1, "maximum": 5},
                    "invalidators": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "related_ids": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {"type": "string"},
                    },
                    "deduplicate": {"type": "boolean"},
                },
            },
            _remember_memory,
        ),
        McpToolSpec(
            "memory_index",
            "Cheap first-stage project-memory lookup returning compact metadata only.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "kind": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "include_stale": {"type": "boolean"},
                },
            },
            _memory_index,
        ),
        McpToolSpec(
            "memory_search",
            "Second-stage project-memory search returning claims and bounded snippets.",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "kind": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                    "include_stale": {"type": "boolean"},
                },
            },
            _memory_search,
        ),
        McpToolSpec(
            "memory_get",
            "Fetch full project-memory records by id after discovery confirms relevance.",
            {
                "type": "object",
                "required": ["ids"],
                "properties": {
                    "ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 20,
                        "items": {"type": "string"},
                    },
                    "include_stale": {"type": "boolean"},
                },
            },
            _memory_get,
        ),
        McpToolSpec(
            "recover_context",
            "Recover exact bytes or one JSON-Pointer subtree from typed ACCO recovery.",
            {
                "type": "object",
                "required": ["handle"],
                "properties": {
                    "handle": {
                        "type": "string",
                        "pattern": "^(?:tsr_[0-9a-f]{32}|tsr_obj_[0-9a-f]{32}|tsr://tsr_obj_[0-9a-f]{32}(?:/.*)?)$"
                    },
                    "pointer": {"type": "string"}
                },
            },
            _recover_context,
        ),
        McpToolSpec(
            "recovery_status",
            "Report project recovery-store capacity and record counts without returning source bytes.",
            {"type": "object", "properties": {}},
            _recovery_status,
        ),
        McpToolSpec(
            "prefix_status",
            "Report stable provider-prefix reuse counters without request content.",
            {"type": "object", "properties": {}},
            _prefix_status,
        ),
        McpToolSpec(
            "discover_tools",
            "Select a bounded specialist MCP tool set for the current task and return its schemas.",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "max_tools": {"type": "integer", "minimum": 7, "maximum": 24},
                },
            },
            _discover_tools,
        ),
        McpToolSpec(
            "build_diff_context",
            "Build context around the current Git patch and its impact closure.",
            {
                "type": "object",
                "properties": {
                    "base": {"type": "string"},
                    "staged": {"type": "boolean"},
                    "max_tokens": {"type": "integer", "minimum": 1},
                },
            },
            _build_diff_context,
        ),
        McpToolSpec(
            "review_diff",
            "Report changed symbols, impact, API changes, and test coverage signals.",
            {
                "type": "object",
                "properties": {
                    "base": {"type": "string"},
                    "staged": {"type": "boolean"},
                },
            },
            _review_diff,
        ),
        McpToolSpec(
            "route_task",
            "Choose the cheapest policy-eligible model for a task using the fresh pricing registry.",
            {
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string"},
                    "input_tokens": {"type": "integer", "minimum": 1},
                    "output_tokens": {"type": "integer", "minimum": 1},
                    "current_model": {"type": "string"},
                    "allowed_models": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "min_savings": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "conservative": {"type": "boolean"},
                    "calibration_file": {"type": "string"},
                },
            },
            _route_task,
        ),
        McpToolSpec(
            "execute",
            (
                "Run restricted Python analysis over explicitly selected repository "
                "text files outside model context. Inputs are exposed as the data/files "
                "mapping keyed by repository-relative path; assign the JSON-safe answer "
                "to result. Imports, shell/process access, arbitrary file access, and "
                "private/dunder traversal are blocked. Oversized results are exactly "
                "recoverable."
            ),
            {
                "type": "object",
                "required": ["code", "files"],
                "properties": {
                    "code": {
                        "type": "string",
                        "maxLength": 16000,
                        "description": (
                            "Restricted Python program. Read selected text through "
                            "data[path] or files[path] and assign the answer to result."
                        ),
                    },
                    "files": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 128,
                        "items": {"type": "string"},
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 30,
                    },
                    "max_result_bytes": {
                        "type": "integer",
                        "minimum": 1024,
                        "maximum": 1048576,
                    },
                },
            },
            _execute,
        ),
        McpToolSpec(
            "execute_file",
            (
                "Run a repository-contained restricted Python program over explicit "
                "repository text inputs outside model context."
            ),
            {
                "type": "object",
                "required": ["program_file", "files"],
                "properties": {
                    "program_file": {"type": "string"},
                    "files": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 128,
                        "items": {"type": "string"},
                    },
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
                    "max_result_bytes": {"type": "integer", "minimum": 1024, "maximum": 1048576},
                },
            },
            _execute_file,
        ),
        McpToolSpec(
            "batch_execute",
            (
                "Run up to eight restricted out-of-context analysis jobs. Each job "
                "provides exactly one of code/code_file plus explicit text files."
            ),
            {
                "type": "object",
                "required": ["jobs"],
                "properties": {
                    "jobs": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "required": ["files"],
                            "properties": {
                                "id": {"type": "string"},
                                "code": {"type": "string"},
                                "code_file": {"type": "string"},
                                "files": {
                                    "type": "array",
                                    "minItems": 1,
                                    "maxItems": 128,
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
                    "max_result_bytes": {"type": "integer", "minimum": 1024, "maximum": 1048576},
                },
            },
            _batch_execute,
        ),
        McpToolSpec(
            "session_search",
            "Search redacted structured session history with local FTS5 when available.",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "kinds": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "session": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            _session_search,
        ),
        McpToolSpec(
            "session_recent",
            "Return recent structured session events without raw prompt/tool-output text.",
            {
                "type": "object",
                "properties": {
                    "kinds": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "session": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            _session_recent,
        ),
        McpToolSpec(
            "output_policy",
            "Return a generation-time response policy for reducing output tokens.",
            {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["terse", "normal", "detailed"],
                    },
                    "max_tokens": {"type": "integer", "minimum": 1},
                    "task": {
                        "type": "string",
                        "enum": [
                            "general",
                            "coding",
                            "debugging",
                            "review",
                            "explanation",
                            "planning",
                        ],
                    },
                },
            },
            _output_policy,
        ),
        McpToolSpec(
            "compact_output",
            "Safely compact generated prose while preserving fenced code/diffs exactly.",
            {
                "type": "object",
                "required": ["text"],
                "properties": {
                    "text": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["terse", "normal", "detailed"],
                    },
                    "max_tokens": {"type": "integer", "minimum": 1},
                    "enforce_budget": {"type": "boolean"},
                },
            },
            _compact_output,
        ),
    ]
)


MCP_TOOL_PROFILES = {
    "minimal": (
        "route_task",
        "build_context",
        "find_symbol",
        "browse_context",
        "recall_findings",
        "remember_finding",
    ),
    "context": (
        "route_task",
        "build_context",
        "find_symbol",
        "browse_context",
        "explain_ranking",
        "analyze_change_impact",
        "report_context_feedback",
        "index_status",
        "refresh_index",
        "semantic_index_status",
        "refresh_semantic_index",
        "recall_findings",
        "remember_finding",
        "knowledge_status",
        "memory_index",
        "memory_search",
        "memory_get",
        "remember_memory",
        "session_search",
        "session_recent",
        "execute",
        "execute_file",
        "batch_execute",
    ),
    "memory": (
        "build_context",
        "find_symbol",
        "memory_index",
        "memory_search",
        "memory_get",
        "remember_memory",
        "knowledge_status",
        "session_search",
        "session_recent",
    ),
    "adaptive": ADAPTIVE_CORE,
}


def tool_registry_for_profile(profile: str) -> McpToolRegistry:
    """Return the bounded default MCP registry for one advertised profile."""
    normalized = profile.strip().lower()
    if normalized == "full":
        return DEFAULT_TOOL_REGISTRY
    names = MCP_TOOL_PROFILES.get(normalized)
    if names is None:
        allowed = ", ".join([*MCP_TOOL_PROFILES, "full"])
        raise ValueError(f"unknown MCP tool profile {profile!r}; expected one of: {allowed}")
    registry = DEFAULT_TOOL_REGISTRY.select(names)
    missing = [name for name in names if name not in registry.names()]
    if missing:
        raise RuntimeError(
            "MCP tool profile references unavailable tools: " + ", ".join(missing)
        )
    return registry
