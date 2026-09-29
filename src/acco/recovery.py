"""Content-addressed exact and typed recovery for lossy ACCO transforms."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

from .state import state_dir

DEFAULT_CAPACITY_BYTES = 512 * 1024 * 1024
_HANDLE_PREFIX = "tsr_"
_OBJECT_PREFIX = "tsr_obj_"


class RecoveryCapacityError(RuntimeError):
    """Raised when adding a payload would exceed the configured recovery cap."""


class RecoveryIntegrityError(RuntimeError):
    """Raised when stored recovery bytes or database identity cannot be trusted."""


@dataclass(frozen=True)
class RecoveryRecord:
    """Metadata plus exact recovered bytes for one content-addressed payload."""

    handle: str
    content_type: str
    payload: bytes
    metadata: dict
    created_at: int
    last_accessed_at: int | None
    access_count: int

    @property
    def size_bytes(self) -> int:
        """Return exact payload size."""
        return len(self.payload)


@dataclass(frozen=True)
class TypedRecoveryRecord:
    """One exact canonical JSON object stored for selective recovery."""

    handle: str
    object_type: str
    value: Any
    metadata: dict
    created_at: int
    last_accessed_at: int | None
    access_count: int
    digest: str

    @property
    def size_bytes(self) -> int:
        """Return canonical serialized object size."""
        return len(_canonical_json(self.value))


def _project_id(root: Path) -> str:
    """Return an opaque stable identifier for one project root."""
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]


def recovery_path(root: Path) -> Path:
    """Return the private project-scoped recovery database path."""
    return state_dir() / "recovery" / f"{_project_id(root)}.sqlite3"


def recovery_handle(payload: bytes) -> str:
    """Return a deterministic content-addressed handle for exact bytes."""
    digest = hashlib.sha256(payload).hexdigest()
    return _HANDLE_PREFIX + digest[:32]


def object_recovery_handle(value: Any) -> str:
    """Return a deterministic typed-object handle for canonical JSON."""
    digest = hashlib.sha256(_canonical_json(value)).hexdigest()
    return _OBJECT_PREFIX + digest[:32]


def _canonical_json(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes or reject unsupported values."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("typed recovery value must be finite JSON") from exc


def _metadata_json(metadata: dict | None) -> str:
    """Serialize metadata deterministically."""
    try:
        return json.dumps(
            metadata or {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("recovery metadata must be finite JSON") from exc


def _stat_identity(path: Path) -> tuple[int, int] | None:
    """Return stable device/inode identity when the platform exposes it."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    inode = int(getattr(stat, "st_ino", 0) or 0)
    device = int(getattr(stat, "st_dev", 0) or 0)
    if not inode:
        return None
    return device, inode


def _decode_pointer_token(token: str) -> str:
    """Decode one RFC 6901 JSON Pointer token."""
    return token.replace("~1", "/").replace("~0", "~")


def _select_pointer(value: Any, pointer: str) -> Any:
    """Select one JSON Pointer subtree from a typed recovery object."""
    if pointer in {"", "/"}:
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("recovery selector must be an RFC 6901 JSON Pointer")
    current = value
    for raw in pointer.split("/")[1:]:
        token = _decode_pointer_token(raw)
        if isinstance(current, dict):
            if token not in current:
                raise KeyError(pointer)
            current = current[token]
            continue
        if isinstance(current, list):
            if token == "-":
                raise KeyError(pointer)
            try:
                index = int(token)
            except ValueError as exc:
                raise KeyError(pointer) from exc
            if index < 0 or index >= len(current):
                raise KeyError(pointer)
            current = current[index]
            continue
        raise KeyError(pointer)
    return current


class RecoveryStore:
    """Persist exact source before lossy transforms and recover it safely."""

    def __init__(
        self,
        root: Path,
        *,
        capacity_bytes: int = DEFAULT_CAPACITY_BYTES,
    ):
        """Create one project-scoped recovery store."""
        if capacity_bytes <= 0:
            raise ValueError("recovery capacity_bytes must be positive")
        self.root = root.resolve()
        self.path = recovery_path(self.root)
        self.capacity_bytes = int(capacity_bytes)

    def _connect(self) -> sqlite3.Connection:
        """Open, initialize, and integrity-check the private SQLite store."""
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        before = _stat_identity(self.path)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recovery (
                handle TEXT PRIMARY KEY,
                digest TEXT NOT NULL,
                content_type TEXT NOT NULL,
                payload BLOB NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_accessed_at INTEGER,
                access_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recovery_objects (
                handle TEXT PRIMARY KEY,
                digest TEXT NOT NULL,
                object_type TEXT NOT NULL,
                payload_json BLOB NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_accessed_at INTEGER,
                access_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recovery_dependencies (
                owner_handle TEXT NOT NULL,
                dependency_handle TEXT NOT NULL,
                PRIMARY KEY(owner_handle, dependency_handle)
            )
            """
        )
        connection.commit()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        after = _stat_identity(self.path)
        if before is not None and after is not None and before != after:
            connection.close()
            raise RecoveryIntegrityError(
                "recovery database identity changed while opening"
            )
        integrity = connection.execute("PRAGMA quick_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            connection.close()
            raise RecoveryIntegrityError("recovery database integrity check failed")
        return connection

    def _used_bytes(self, connection: sqlite3.Connection) -> int:
        """Return bytes reserved by exact and typed recovery records."""
        exact = connection.execute(
            "SELECT COALESCE(SUM(length(payload)), 0) FROM recovery"
        ).fetchone()[0]
        typed = connection.execute(
            "SELECT COALESCE(SUM(length(payload_json)), 0) FROM recovery_objects"
        ).fetchone()[0]
        return int(exact or 0) + int(typed or 0)

    def _assert_capacity(
        self,
        connection: sqlite3.Connection,
        additional_bytes: int,
    ) -> None:
        """Refuse new lossy state rather than evicting existing recovery."""
        if self._used_bytes(connection) + int(additional_bytes) > self.capacity_bytes:
            raise RecoveryCapacityError(
                "recovery capacity exceeded; original payload was not transformed"
            )

    def put(
        self,
        payload: bytes | str,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
        dependencies: list[str] | tuple[str, ...] | None = None,
    ) -> str:
        """Store exact bytes before transformation without evicting older records."""
        raw = payload.encode() if isinstance(payload, str) else bytes(payload)
        handle = recovery_handle(raw)
        digest = hashlib.sha256(raw).hexdigest()
        encoded_metadata = _metadata_json(metadata)
        now = int(time.time())
        with closing(self._connect()) as connection:
            existing = connection.execute(
                "SELECT digest FROM recovery WHERE handle = ?",
                (handle,),
            ).fetchone()
            if existing:
                if str(existing[0]) != digest:
                    raise RecoveryIntegrityError("recovery handle digest collision")
                return handle
            self._assert_capacity(connection, len(raw))
            connection.execute(
                """
                INSERT INTO recovery (
                    handle, digest, content_type, payload, metadata_json,
                    created_at, last_accessed_at, access_count
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0)
                """,
                (
                    handle,
                    digest,
                    content_type,
                    sqlite3.Binary(raw),
                    encoded_metadata,
                    now,
                ),
            )
            self._store_dependencies(connection, handle, dependencies)
            connection.commit()
        return handle

    def put_object(
        self,
        value: Any,
        *,
        object_type: str = "json",
        metadata: dict | None = None,
        dependencies: list[str] | tuple[str, ...] | None = None,
    ) -> str:
        """Store canonical JSON so agents can recover only a selected subtree."""
        raw = _canonical_json(value)
        handle = object_recovery_handle(value)
        digest = hashlib.sha256(raw).hexdigest()
        now = int(time.time())
        with closing(self._connect()) as connection:
            existing = connection.execute(
                "SELECT digest FROM recovery_objects WHERE handle = ?",
                (handle,),
            ).fetchone()
            if existing:
                if str(existing[0]) != digest:
                    raise RecoveryIntegrityError(
                        "typed recovery handle digest collision"
                    )
                return handle
            self._assert_capacity(connection, len(raw))
            connection.execute(
                """
                INSERT INTO recovery_objects (
                    handle, digest, object_type, payload_json, metadata_json,
                    created_at, last_accessed_at, access_count
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0)
                """,
                (
                    handle,
                    digest,
                    str(object_type or "json")[:120],
                    sqlite3.Binary(raw),
                    _metadata_json(metadata),
                    now,
                ),
            )
            self._store_dependencies(connection, handle, dependencies)
            connection.commit()
        return handle

    def _store_dependencies(
        self,
        connection: sqlite3.Connection,
        owner_handle: str,
        dependencies: list[str] | tuple[str, ...] | None,
    ) -> None:
        """Attach existing recovery dependencies to one owner record."""
        for dependency in dict.fromkeys(dependencies or ()):
            dep = str(dependency)
            exists = connection.execute(
                """
                SELECT 1 FROM recovery WHERE handle = ?
                UNION ALL
                SELECT 1 FROM recovery_objects WHERE handle = ?
                LIMIT 1
                """,
                (dep, dep),
            ).fetchone()
            if exists is None:
                raise KeyError(dep)
            connection.execute(
                """
                INSERT OR IGNORE INTO recovery_dependencies(
                    owner_handle, dependency_handle
                ) VALUES (?, ?)
                """,
                (owner_handle, dep),
            )

    def get(self, handle: str) -> RecoveryRecord:
        """Return exact stored bytes and record bounded access telemetry."""
        if not isinstance(handle, str) or not handle.startswith(_HANDLE_PREFIX):
            raise ValueError("invalid recovery handle")
        if handle.startswith(_OBJECT_PREFIX):
            raise ValueError("typed recovery handle requires get_object/select")
        now = int(time.time())
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT handle, content_type, payload, metadata_json, created_at,
                       last_accessed_at, access_count, digest
                FROM recovery WHERE handle = ?
                """,
                (handle,),
            ).fetchone()
            if row is None:
                raise KeyError(handle)
            payload = bytes(row[2])
            if hashlib.sha256(payload).hexdigest() != row[7]:
                raise RecoveryIntegrityError(
                    "recovery payload integrity check failed"
                )
            count = int(row[6] or 0) + 1
            connection.execute(
                """
                UPDATE recovery
                SET last_accessed_at = ?, access_count = ?
                WHERE handle = ?
                """,
                (now, count, handle),
            )
            connection.commit()
        metadata = json.loads(row[3])
        if not isinstance(metadata, dict):
            metadata = {}
        return RecoveryRecord(
            handle=row[0],
            content_type=row[1],
            payload=payload,
            metadata=metadata,
            created_at=int(row[4]),
            last_accessed_at=now,
            access_count=count,
        )

    def get_object(self, handle: str) -> TypedRecoveryRecord:
        """Return one exact typed object with digest verification."""
        if not isinstance(handle, str) or not handle.startswith(_OBJECT_PREFIX):
            raise ValueError("invalid typed recovery handle")
        now = int(time.time())
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT handle, object_type, payload_json, metadata_json,
                       created_at, last_accessed_at, access_count, digest
                FROM recovery_objects WHERE handle = ?
                """,
                (handle,),
            ).fetchone()
            if row is None:
                raise KeyError(handle)
            payload = bytes(row[2])
            digest = hashlib.sha256(payload).hexdigest()
            if digest != str(row[7]):
                raise RecoveryIntegrityError(
                    "typed recovery payload integrity check failed"
                )
            try:
                value = json.loads(payload)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RecoveryIntegrityError(
                    "typed recovery payload is not valid canonical JSON"
                ) from exc
            count = int(row[6] or 0) + 1
            connection.execute(
                """
                UPDATE recovery_objects
                SET last_accessed_at = ?, access_count = ?
                WHERE handle = ?
                """,
                (now, count, handle),
            )
            connection.commit()
        metadata = json.loads(row[3])
        if not isinstance(metadata, dict):
            metadata = {}
        return TypedRecoveryRecord(
            handle=str(row[0]),
            object_type=str(row[1]),
            value=value,
            metadata=metadata,
            created_at=int(row[4]),
            last_accessed_at=now,
            access_count=count,
            digest=digest,
        )

    def select(self, reference: str, pointer: str | None = None) -> dict[str, Any]:
        """Recover a typed object or one RFC 6901 subtree."""
        handle = reference
        selected_pointer = pointer
        if reference.startswith("tsr://"):
            remainder = reference[len("tsr://") :]
            slash = remainder.find("/")
            if slash < 0:
                handle = remainder
                selected_pointer = ""
            else:
                handle = remainder[:slash]
                selected_pointer = remainder[slash:]
        record = self.get_object(handle)
        selected = _select_pointer(record.value, selected_pointer or "")
        return {
            "handle": record.handle,
            "reference": f"tsr://{record.handle}{selected_pointer or ''}",
            "pointer": selected_pointer or "",
            "object_type": record.object_type,
            "value": selected,
            "metadata": record.metadata,
            "access_count": record.access_count,
        }

    def dependencies(self, handle: str) -> list[str]:
        """Return exact recovery handles this record depends on."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT dependency_handle
                FROM recovery_dependencies
                WHERE owner_handle = ?
                ORDER BY dependency_handle
                """,
                (handle,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def info(self, handle: str) -> dict:
        """Return metadata without returning payload bytes."""
        with closing(self._connect()) as connection:
            if handle.startswith(_OBJECT_PREFIX):
                row = connection.execute(
                    """
                    SELECT handle, object_type, length(payload_json), metadata_json,
                           created_at, last_accessed_at, access_count, digest
                    FROM recovery_objects WHERE handle = ?
                    """,
                    (handle,),
                ).fetchone()
                if row is None:
                    raise KeyError(handle)
                metadata = json.loads(row[3])
                return {
                    "handle": row[0],
                    "kind": "object",
                    "object_type": row[1],
                    "size_bytes": int(row[2]),
                    "metadata": metadata if isinstance(metadata, dict) else {},
                    "created_at": int(row[4]),
                    "last_accessed_at": row[5],
                    "access_count": int(row[6] or 0),
                    "digest": row[7],
                    "dependencies": self.dependencies(handle),
                }
            row = connection.execute(
                """
                SELECT handle, content_type, length(payload), metadata_json,
                       created_at, last_accessed_at, access_count, digest
                FROM recovery WHERE handle = ?
                """,
                (handle,),
            ).fetchone()
        if row is None:
            raise KeyError(handle)
        metadata = json.loads(row[3])
        return {
            "handle": row[0],
            "kind": "bytes",
            "content_type": row[1],
            "size_bytes": int(row[2]),
            "metadata": metadata if isinstance(metadata, dict) else {},
            "created_at": int(row[4]),
            "last_accessed_at": row[5],
            "access_count": int(row[6] or 0),
            "digest": row[7],
            "dependencies": self.dependencies(handle),
        }

    def stats(self) -> dict:
        """Return capacity and record counts without exposing recovered content."""
        with closing(self._connect()) as connection:
            exact = connection.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(length(payload)), 0)
                FROM recovery
                """
            ).fetchone()
            typed = connection.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(length(payload_json)), 0)
                FROM recovery_objects
                """
            ).fetchone()
            dependencies = connection.execute(
                "SELECT COUNT(*) FROM recovery_dependencies"
            ).fetchone()[0]
        used = int(exact[1] or 0) + int(typed[1] or 0)
        return {
            "path": str(self.path),
            "records": int(exact[0] or 0) + int(typed[0] or 0),
            "byte_records": int(exact[0] or 0),
            "object_records": int(typed[0] or 0),
            "dependencies": int(dependencies or 0),
            "used_bytes": used,
            "capacity_bytes": self.capacity_bytes,
            "remaining_bytes": max(0, self.capacity_bytes - used),
        }
