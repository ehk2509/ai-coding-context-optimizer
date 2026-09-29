"""Local learned importance for structured tool-result fields."""

from __future__ import annotations

from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any

from .state import state_dir

MAX_FIELDS_PER_OBSERVATION = 256
MAX_DEPTH = 5
_DEFAULT_MIN_EXPOSURES = 3
_DEFAULT_MIN_RETRIEVALS = 2
_DEFAULT_MIN_CONFIDENCE = 0.30
_SAFE_TOOL = re.compile(r"^[A-Za-z0-9_.:/-]{1,96}$")


def _project_id(root: Path) -> str:
    """Return an opaque stable identifier for one project root."""
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]


def field_learning_path(root: Path) -> Path:
    """Return the private SQLite path for one project's field-learning state."""
    return state_dir() / "tool-fields" / f"{_project_id(root)}.sqlite3"


def normalize_tool_key(tool: str) -> str:
    """Return a bounded non-secret tool identity suitable for local statistics."""
    value = str(tool or "generic-json").strip()
    if _SAFE_TOOL.fullmatch(value):
        return value
    return "tool-" + hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:20]


def _connect(root: Path) -> sqlite3.Connection:
    """Open and initialize the private field-learning database."""
    path = field_learning_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS field_stats (
            tool_key TEXT NOT NULL,
            field_path TEXT NOT NULL,
            exposures INTEGER NOT NULL DEFAULT 0,
            retrievals INTEGER NOT NULL DEFAULT 0,
            last_seen INTEGER NOT NULL,
            PRIMARY KEY(tool_key, field_path)
        )
        """
    )
    connection.commit()
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return connection


def _field_paths(value: Any, path: str = "$", depth: int = 0) -> list[str]:
    """Return bounded structural field paths without storing any field values."""
    if depth >= MAX_DEPTH:
        return []
    out: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            token = str(key).replace("~", "~0").replace("/", "~1")[:120]
            child = f"{path}/{token}"
            out.append(child)
            if len(out) >= MAX_FIELDS_PER_OBSERVATION:
                break
            out.extend(_field_paths(item, child, depth + 1))
            if len(out) >= MAX_FIELDS_PER_OBSERVATION:
                break
    elif isinstance(value, list) and value:
        sample = value[: min(4, len(value))]
        child = f"{path}/*"
        for item in sample:
            out.extend(_field_paths(item, child, depth + 1))
            if len(out) >= MAX_FIELDS_PER_OBSERVATION:
                break
    return list(dict.fromkeys(out[:MAX_FIELDS_PER_OBSERVATION]))


def observe_tool_json(root: Path, tool: str, value: Any) -> int:
    """Record field exposure counts for one structured tool payload."""
    fields = _field_paths(value)
    if not fields:
        return 0
    key = normalize_tool_key(tool)
    now = int(time.time())
    try:
        with closing(_connect(root)) as connection:
            for field_path in fields:
                connection.execute(
                    """
                    INSERT INTO field_stats(tool_key, field_path, exposures, retrievals, last_seen)
                    VALUES (?, ?, 1, 0, ?)
                    ON CONFLICT(tool_key, field_path) DO UPDATE SET
                        exposures = exposures + 1,
                        last_seen = excluded.last_seen
                    """,
                    (key, field_path, now),
                )
            connection.commit()
    except sqlite3.Error:
        return 0
    return len(fields)


def _pointer_candidates(pointer: str) -> list[str]:
    """Return structural paths implied by one RFC 6901 pointer."""
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return []
    parts = [part for part in pointer.split("/")[1:] if part]
    path = "$"
    candidates: list[str] = []
    for part in parts:
        token = part
        if token.isdigit():
            token = "*"
        path += "/" + token[:120]
        candidates.append(path)
    return candidates


def record_field_retrieval(root: Path, tool: str, pointer: str) -> int:
    """Record selective-recovery evidence for fields the model actually requested."""
    candidates = _pointer_candidates(pointer)
    if not candidates:
        return 0
    key = normalize_tool_key(tool)
    now = int(time.time())
    updated = 0
    try:
        with closing(_connect(root)) as connection:
            for field_path in candidates:
                cursor = connection.execute(
                    """
                    UPDATE field_stats
                    SET retrievals = retrievals + 1, last_seen = ?
                    WHERE tool_key = ? AND field_path = ?
                    """,
                    (now, key, field_path),
                )
                updated += int(cursor.rowcount or 0)
            connection.commit()
    except sqlite3.Error:
        return 0
    return updated


def field_hints(
    root: Path,
    tool: str,
    *,
    min_exposures: int = _DEFAULT_MIN_EXPOSURES,
    min_retrievals: int = _DEFAULT_MIN_RETRIEVALS,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
    limit: int = 16,
) -> list[dict[str, Any]]:
    """Return field paths with enough local retrieval evidence to influence packing."""
    if min_exposures <= 0 or min_retrievals <= 0 or limit <= 0:
        raise ValueError("field-learning thresholds and limit must be positive")
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")
    key = normalize_tool_key(tool)
    try:
        with closing(_connect(root)) as connection:
            rows = connection.execute(
                """
                SELECT field_path, exposures, retrievals, last_seen
                FROM field_stats
                WHERE tool_key = ? AND exposures >= ? AND retrievals >= ?
                ORDER BY retrievals DESC, exposures DESC, field_path ASC
                LIMIT ?
                """,
                (key, int(min_exposures), int(min_retrievals), int(limit * 4)),
            ).fetchall()
    except sqlite3.Error:
        return []
    hints: list[dict[str, Any]] = []
    for row in rows:
        exposures = max(1, int(row["exposures"]))
        retrievals = int(row["retrievals"])
        confidence = min(1.0, retrievals / exposures)
        if confidence < min_confidence:
            continue
        hints.append(
            {
                "field_path": str(row["field_path"]),
                "exposures": exposures,
                "retrievals": retrievals,
                "confidence": confidence,
                "last_seen": int(row["last_seen"]),
            }
        )
        if len(hints) >= limit:
            break
    return hints


def important_field_names(root: Path, tool: str) -> set[str]:
    """Return learned terminal field names for conservative JSON preservation."""
    names: set[str] = set()
    for hint in field_hints(root, tool):
        token = str(hint["field_path"]).rsplit("/", 1)[-1]
        if token and token != "*":
            names.add(token.replace("~1", "/").replace("~0", "~"))
    return names


def field_learning_report(root: Path, *, limit: int = 50) -> dict[str, Any]:
    """Return content-free learned-field statistics for diagnostics."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    with closing(_connect(root)) as connection:
        rows = connection.execute(
            """
            SELECT tool_key, field_path, exposures, retrievals, last_seen
            FROM field_stats
            WHERE retrievals > 0
            ORDER BY retrievals DESC, exposures DESC, tool_key, field_path
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        tools = connection.execute(
            "SELECT COUNT(DISTINCT tool_key) FROM field_stats"
        ).fetchone()[0]
    return {
        "schema": 1,
        "tools": int(tools or 0),
        "fields": [
            {
                "tool": str(row["tool_key"]),
                "field_path": str(row["field_path"]),
                "exposures": int(row["exposures"]),
                "retrievals": int(row["retrievals"]),
                "confidence": min(
                    1.0,
                    int(row["retrievals"]) / max(1, int(row["exposures"])),
                ),
                "last_seen": int(row["last_seen"]),
            }
            for row in rows
        ],
        "privacy": "Only tool identities, structural field paths, and counters are stored.",
    }
