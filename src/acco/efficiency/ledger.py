"""Searchable project-scoped session event ledger.

The ledger complements ACCO's compact continuity snapshot and telemetry JSONL.
It stores bounded, redacted *structured* working-state events in SQLite and
indexes their short summaries with FTS5 when the local sqlite build supports it.

It is intentionally not a transcript store: raw prompts and raw tool outputs are
never persisted here. Prompt text contributes only narrowly extracted explicit
decision/preference snippets after secret redaction.
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any

from ..state import state_dir

SCHEMA = 1
MAX_EVENTS = 20_000
MAX_SUMMARY_CHARS = 320
MAX_METADATA_BYTES = 4096
DEFAULT_SEARCH_LIMIT = 12
MAX_SEARCH_LIMIT = 50

_SECRET_RE = re.compile(
    r"(?i)(?:(password|passwd|token|secret|api[_-]?key)\s*[=:]\s*)(\S+)"
)
_SECRET_FLAG_RE = re.compile(
    r"(?i)(--(?:password|passwd|token|secret|api[-_]?key|authorization)\s+)(\S+)"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)(authorization\s*:\s*)(?:bearer\s+)?(\S+)"
)
_URL_CREDS_RE = re.compile(r"(https?://[^:/\s]+:)[^@/\s]+@")
_DECISION_RE = re.compile(
    r"(?i)\b(?:use|prefer|choose|keep|avoid|do not|don't|must|should|instead|"
    r"decision\s*:|remember\s+that|stick\s+with)\b"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _project_id(root: Path) -> str:
    """Return a stable opaque project identifier."""
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]


def ledger_path(root: Path) -> Path:
    """Return the private SQLite ledger path for one repository."""
    return state_dir() / "session-ledger" / f"{_project_id(root)}.sqlite3"


def _redact(value: str, *, limit: int = MAX_SUMMARY_CHARS) -> str:
    """Return compact text with common credential forms removed."""
    text = " ".join(str(value).strip().split())

    def redact(match: re.Match[str]) -> str:
        return match.group(0).replace(match.group(2), "<redacted>")

    text = _SECRET_RE.sub(redact, text)
    text = _SECRET_FLAG_RE.sub(redact, text)
    text = _AUTH_HEADER_RE.sub(redact, text)
    text = _URL_CREDS_RE.sub(r"\1<redacted>@", text)
    return text[:limit]


def decision_summaries(prompt: str, *, limit: int = 3) -> list[str]:
    """Extract only explicit decision/preference sentences from a prompt."""
    results: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(prompt):
        candidate = sentence.strip()
        if not candidate or not _DECISION_RE.search(candidate):
            continue
        cleaned = _redact(candidate, limit=240)
        if cleaned and cleaned not in results:
            results.append(cleaned)
        if len(results) >= limit:
            break
    return results


def _metadata_json(metadata: dict[str, Any] | None) -> str:
    """Serialize bounded JSON metadata without allowing large payload storage."""
    if not metadata:
        return "{}"
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)[:80]] = (
                _redact(value, limit=240) if isinstance(value, str) else value
            )
    raw = json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(raw.encode("utf-8")) > MAX_METADATA_BYTES:
        return json.dumps({"truncated": True}, separators=(",", ":"))
    return raw


def _connect(root: Path) -> sqlite3.Connection:
    """Open and initialize one private project ledger."""
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schema INTEGER NOT NULL,
            recorded_at INTEGER NOT NULL,
            session TEXT,
            turn INTEGER,
            kind TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL,
            path TEXT,
            status TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_time ON events(recorded_at DESC, id DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_session ON events(session, id DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind, id DESC)"
    )
    try:
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS events_fts
            USING fts5(summary, subject, path, content='events', content_rowid='id')
            """
        )
        connection.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
              INSERT INTO events_fts(rowid, summary, subject, path)
              VALUES (new.id, new.summary, new.subject, COALESCE(new.path, ''));
            END;
            CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
              INSERT INTO events_fts(events_fts, rowid, summary, subject, path)
              VALUES ('delete', old.id, old.summary, old.subject, COALESCE(old.path, ''));
            END;
            CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
              INSERT INTO events_fts(events_fts, rowid, summary, subject, path)
              VALUES ('delete', old.id, old.summary, old.subject, COALESCE(old.path, ''));
              INSERT INTO events_fts(rowid, summary, subject, path)
              VALUES (new.id, new.summary, new.subject, COALESCE(new.path, ''));
            END;
            """
        )
    except sqlite3.OperationalError:
        # Some minimal Python/sqlite builds omit FTS5. Search falls back to LIKE.
        pass
    connection.commit()
    if path.exists():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return connection


def _fts_available(connection: sqlite3.Connection) -> bool:
    """Return whether the FTS table exists in this sqlite build."""
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events_fts'"
    ).fetchone()
    return row is not None


def append_ledger_event(
    root: Path,
    *,
    kind: str,
    summary: str,
    session: str | None = None,
    turn: int | None = None,
    subject: str = "",
    path: str | None = None,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Append one bounded redacted working-state event and return its id."""
    root = Path(root).resolve()
    safe_summary = _redact(summary)
    if not safe_summary:
        raise ValueError("ledger event summary must be nonempty")
    safe_subject = _redact(subject, limit=120)
    safe_path = _redact(path, limit=300) if path else None
    safe_status = _redact(status, limit=80) if status else None

    with closing(_connect(root)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO events(
                schema, recorded_at, session, turn, kind, subject,
                summary, path, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SCHEMA,
                int(time.time()),
                session,
                int(turn) if turn is not None else None,
                _redact(kind, limit=80),
                safe_subject,
                safe_summary,
                safe_path,
                safe_status,
                _metadata_json(metadata),
            ),
        )
        event_id = int(cursor.lastrowid)
        excess = connection.execute(
            "SELECT COUNT(*) - ? FROM events",
            (MAX_EVENTS,),
        ).fetchone()[0]
        if isinstance(excess, int) and excess > 0:
            connection.execute(
                """
                DELETE FROM events
                WHERE id IN (SELECT id FROM events ORDER BY id ASC LIMIT ?)
                """,
                (excess,),
            )
        connection.commit()
        return event_id


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert one sqlite row into the public structured event shape."""
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except (TypeError, ValueError):
        metadata = {}
    return {
        "id": int(row["id"]),
        "recorded_at": int(row["recorded_at"]),
        "session": row["session"],
        "turn": row["turn"],
        "kind": row["kind"],
        "subject": row["subject"],
        "summary": row["summary"],
        "path": row["path"],
        "status": row["status"],
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


def recent_ledger_events(
    root: Path,
    *,
    session: str | None = None,
    kinds: tuple[str, ...] | list[str] | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, Any]]:
    """Return newest structured ledger events without transcript content."""
    limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
    where: list[str] = []
    params: list[Any] = []
    if session:
        where.append("session = ?")
        params.append(session)
    normalized_kinds = tuple(str(kind) for kind in (kinds or ()) if str(kind))
    if normalized_kinds:
        where.append("kind IN (" + ",".join("?" for _ in normalized_kinds) + ")")
        params.extend(normalized_kinds)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    query = (
        "SELECT * FROM events"
        + clause
        + " ORDER BY recorded_at DESC, id DESC LIMIT ?"
    )
    params.append(limit)
    with closing(_connect(Path(root).resolve())) as connection:
        rows = connection.execute(query, params).fetchall()
    return [_row_dict(row) for row in rows]


def search_ledger(
    root: Path,
    query: str,
    *,
    kinds: tuple[str, ...] | list[str] | None = None,
    session: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> dict[str, Any]:
    """Search session history with FTS5, falling back to bounded LIKE matching."""
    query = " ".join(str(query).split()).strip()
    if not query:
        raise ValueError("session ledger query must be nonempty")
    limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
    normalized_kinds = tuple(str(kind) for kind in (kinds or ()) if str(kind))
    root = Path(root).resolve()

    with closing(_connect(root)) as connection:
        filters: list[str] = []
        params: list[Any] = []
        if session:
            filters.append("e.session = ?")
            params.append(session)
        if normalized_kinds:
            filters.append(
                "e.kind IN (" + ",".join("?" for _ in normalized_kinds) + ")"
            )
            params.extend(normalized_kinds)
        filter_sql = (" AND " + " AND ".join(filters)) if filters else ""

        mode = "like"
        rows: list[sqlite3.Row]
        if _fts_available(connection):
            tokens = re.findall(r"[A-Za-z0-9_./-]+", query)
            expression = " OR ".join(
                f'"{token.replace(chr(34), "")}"' for token in tokens
            )
            if expression:
                try:
                    rows = connection.execute(
                        """
                        SELECT e.*, bm25(events_fts) AS rank
                        FROM events_fts
                        JOIN events e ON e.id = events_fts.rowid
                        WHERE events_fts MATCH ?
                        """
                        + filter_sql
                        + " ORDER BY rank ASC, e.recorded_at DESC LIMIT ?",
                        [expression, *params, limit],
                    ).fetchall()
                    mode = "fts5"
                except sqlite3.OperationalError:
                    rows = []
            else:
                rows = []
        else:
            rows = []

        if not rows:
            like = "%" + query.replace("%", r"\%").replace("_", r"\_") + "%"
            rows = connection.execute(
                """
                SELECT e.*
                FROM events e
                WHERE (
                    e.summary LIKE ? ESCAPE '\\'
                    OR e.subject LIKE ? ESCAPE '\\'
                    OR COALESCE(e.path, '') LIKE ? ESCAPE '\\'
                )
                """
                + filter_sql
                + " ORDER BY e.recorded_at DESC, e.id DESC LIMIT ?",
                [like, like, like, *params, limit],
            ).fetchall()
            mode = "like"

    return {
        "schema": 1,
        "query": query,
        "mode": mode,
        "count": len(rows),
        "events": [_row_dict(row) for row in rows],
    }


def resume_ledger_context(
    root: Path,
    *,
    session: str | None = None,
    limit: int = 12,
) -> str | None:
    """Render a compact recent-event orientation packet for resume/compaction."""
    events = recent_ledger_events(
        root,
        session=session,
        kinds=("decision", "file", "command", "failure", "validation", "checkpoint"),
        limit=limit,
    )
    if not events and session:
        events = recent_ledger_events(
            root,
            kinds=("decision", "file", "command", "failure", "validation", "checkpoint"),
            limit=limit,
        )
    if not events:
        return None

    lines = [
        "ACCO SESSION LEDGER — searchable structured project history, not a transcript."
    ]
    for event in reversed(events):
        stamp = event["kind"]
        status = f" [{event['status']}]" if event.get("status") else ""
        lines.append(f"- {stamp}{status}: {event['summary']}")
    lines.append(
        "Use session_search for older/relevant history; verify repository state "
        "before relying on stale events."
    )
    return "\n".join(lines)
