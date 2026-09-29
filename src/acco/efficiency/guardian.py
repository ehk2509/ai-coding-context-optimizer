"""Pre-compaction checkpointing and cold-resume support."""

from __future__ import annotations

import hashlib
from pathlib import Path
import time

from .ledger import append_ledger_event
from .store import append_event, load_snapshot, update_snapshot

MAX_FILES = 10
MAX_COMMANDS = 6
MAX_FAILURES = 4
MAX_VALIDATIONS = 6


def _session_key(session_id: str | None) -> str:
    """Return the same opaque session key used by the efficiency service."""
    raw = session_id or "unknown"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _latest_session(snapshot: dict, session_id: str | None) -> tuple[str | None, dict]:
    """Resolve the requested session, falling back to the latest project session."""
    sessions = snapshot.get("sessions")
    if not isinstance(sessions, dict):
        return None, {}
    key = _session_key(session_id)
    session = sessions.get(key)
    if isinstance(session, dict):
        return key, session
    last = snapshot.get("last_session")
    if isinstance(last, str) and isinstance(sessions.get(last), dict):
        return last, sessions[last]
    return None, {}


def capture_guardian(
    root: Path,
    *,
    session_id: str | None,
    source: str = "compact",
    enabled: bool = True,
) -> dict | None:
    """Persist a bounded structured checkpoint before host compaction."""
    if not enabled:
        return None
    snapshot = load_snapshot(root)
    key, session = _latest_session(snapshot, session_id)
    if not session:
        return None
    checkpoint = {
        "schema": 1,
        "session": key,
        "source": source,
        "captured_at": int(time.time()),
        "task": session.get("task") or "general",
        "working_files": list(session.get("working_files", []))[-MAX_FILES:],
        "commands": list(session.get("commands", []))[-MAX_COMMANDS:],
        "failures": list(session.get("failures", []))[-MAX_FAILURES:],
        "validations": list(session.get("validations", []))[-MAX_VALIDATIONS:],
        "last_activity": session.get("last_activity"),
    }

    def mutate(payload: dict) -> None:
        payload["guardian"] = checkpoint

    update_snapshot(root, mutate)
    append_event(
        root,
        {
            "kind": "guardian",
            "feature": "precompact_checkpoint",
            "session": key,
            "source": source,
        },
    )
    append_ledger_event(
        root,
        kind="checkpoint",
        session=key,
        subject=source,
        summary=(
            f"pre-compaction checkpoint task={checkpoint['task']} "
            f"files={len(checkpoint['working_files'])} "
            f"commands={len(checkpoint['commands'])} "
            f"failures={len(checkpoint['failures'])}"
        ),
        status="captured",
    )
    return checkpoint


def guardian_report(root: Path) -> dict:
    """Return the current guardian checkpoint without transcript content."""
    checkpoint = load_snapshot(root).get("guardian")
    if not isinstance(checkpoint, dict):
        checkpoint = {}
    return {
        "schema": 1,
        "root": str(root.resolve()),
        "available": bool(checkpoint),
        "checkpoint": checkpoint,
        "privacy": (
            "The checkpoint stores structured file/command/validation metadata only; "
            "raw prompts, assistant prose, and tool output are not persisted."
        ),
    }


def guardian_context(
    root: Path,
    *,
    session_id: str | None,
    source: str,
    enabled: bool = True,
) -> str | None:
    """Render a cold-resume orientation packet from the latest checkpoint."""
    if not enabled or source not in {"resume", "compact"}:
        return None
    snapshot = load_snapshot(root)
    checkpoint = snapshot.get("guardian")
    if not isinstance(checkpoint, dict) or not checkpoint:
        return None

    # Do not let an old compaction snapshot outrank fresher structured work.
    # A checkpoint captured immediately before compaction is at least as new as
    # the session it represents; after new work occurs, normal continuity wins.
    _key, latest = _latest_session(snapshot, session_id)
    captured_at = int(checkpoint.get("captured_at") or 0)
    latest_activity = int(latest.get("last_activity") or 0) if latest else 0
    if latest_activity > captured_at:
        return None

    files = [
        str(item.get("path"))
        for item in checkpoint.get("working_files", [])
        if isinstance(item, dict) and item.get("path")
    ]
    validations = [
        f"{item.get('kind')}={item.get('status')} ({item.get('label')})"
        for item in checkpoint.get("validations", [])
        if isinstance(item, dict)
    ]
    failures = [
        str(item.get("label"))
        for item in checkpoint.get("failures", [])
        if isinstance(item, dict) and item.get("label")
    ]
    commands = [
        str(item.get("label"))
        for item in checkpoint.get("commands", [])
        if isinstance(item, dict) and item.get("label")
    ]
    if not any((files, validations, failures, commands)):
        return None

    lines = [
        "ACCO COMPACTION GUARDIAN — restored structured state, not a transcript.",
        f"Task class: {checkpoint.get('task') or 'general'}.",
    ]
    if files:
        lines.append("Working files: " + ", ".join(files) + ".")
    if validations:
        lines.append("Recent validation: " + "; ".join(validations) + ".")
    if failures:
        lines.append("Recent failures: " + "; ".join(failures) + ".")
    if commands:
        lines.append("Recent commands: " + "; ".join(commands) + ".")
    lines.append(
        "Resume from this orientation, but verify live repository state before "
        "relying on stale command results."
    )
    append_event(
        root,
        {
            "kind": "continuity",
            "feature": "guardian_restore",
            "session": checkpoint.get("session"),
        },
    )
    return "\n".join(lines)
