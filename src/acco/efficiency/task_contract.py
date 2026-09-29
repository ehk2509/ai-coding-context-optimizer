"""Structured task contract and relevance-based session reconstruction."""

from __future__ import annotations

from pathlib import Path
import re
import time

from ..task_checklist import extract_task_checklist
from .ledger import (
    append_ledger_event,
    decision_summaries,
    recent_ledger_events,
    search_ledger,
)
from .store import load_snapshot, update_snapshot

MAX_FILES = 16
MAX_FAILURES = 8
MAX_VALIDATIONS = 8
MAX_CHECKS = 8
_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+)"
)
_SECRET_RE = re.compile(
    r"(?i)(?:(password|passwd|token|secret|api[_-]?key)\s*[=:]\s*)(\S+)"
)


def _redact(text: str, limit: int = 240) -> str:
    """Return bounded credential-redacted task state."""
    compact = " ".join(str(text).split())

    def replace(match: re.Match[str]) -> str:
        """Replace one detected secret while preserving its key name."""
        return match.group(0).replace(match.group(2), "<redacted>")

    return _SECRET_RE.sub(replace, compact)[:limit]


def _prompt_paths(prompt: str) -> list[str]:
    """Extract bounded repository-shaped paths without persisting prompt prose."""
    found: list[str] = []
    for match in _PATH_RE.finditer(prompt):
        value = match.group(1)
        if value not in found:
            found.append(value)
        if len(found) >= 8:
            break
    return found


def _bounded_unique(values: list[str], value: str, limit: int) -> None:
    """Append one unique bounded value."""
    if not value:
        return
    values[:] = [item for item in values if item != value]
    values.append(value)
    if len(values) > limit:
        del values[: len(values) - limit]


def update_contract_from_prompt(
    root: Path,
    session_key: str,
    prompt: str,
    *,
    task_class: str,
) -> None:
    """Refresh structured task state without storing raw prompt prose in snapshot."""
    decisions = decision_summaries(prompt, limit=8)
    checks = extract_task_checklist(prompt)[:MAX_CHECKS]
    paths = _prompt_paths(prompt)
    now = int(time.time())

    def mutate(snapshot: dict) -> None:
        """Update only structured/coarse task state in the continuity snapshot."""
        sessions = snapshot.setdefault("sessions", {})
        session = sessions.setdefault(session_key, {})
        previous = session.get("contract")
        contract = previous if isinstance(previous, dict) else {}
        contract["goal"] = f"{task_class or 'general'} task"
        contract["task_class"] = task_class or "general"
        contract["updated_at"] = now
        contract.setdefault("created_at", now)
        contract["decision_count"] = len(decisions)
        contract["check_count"] = len(checks)
        contract.setdefault("working_files", [])
        contract.setdefault("failures", [])
        contract.setdefault("validations", [])
        for path in paths:
            _bounded_unique(contract["working_files"], path, MAX_FILES)
        session["contract"] = contract

    update_snapshot(root, mutate)

    # Named checks are bounded extracted requirements, not the original prompt.
    # Keep them in the searchable ledger instead of the continuity JSON snapshot.
    for check in checks:
        append_ledger_event(
            root,
            kind="task_check",
            session=session_key,
            subject="named-check",
            status="pending",
            summary=_redact(check, 220),
        )


def update_contract_from_tool(
    root: Path,
    session_key: str,
    *,
    tool: str,
    path: str | None,
    command: str,
    failed: bool,
    validation_kind: str | None,
) -> None:
    """Update files/failures/validations from one tool event."""
    now = int(time.time())

    def mutate(snapshot: dict) -> None:
        """Apply one tool event to bounded structured task state."""
        sessions = snapshot.setdefault("sessions", {})
        session = sessions.setdefault(session_key, {})
        contract = session.get("contract")
        if not isinstance(contract, dict):
            contract = {
                "goal": f"{session.get('task') or 'general'} task",
                "task_class": str(session.get("task") or "general"),
                "created_at": now,
                "decision_count": 0,
                "check_count": 0,
                "working_files": [],
                "failures": [],
                "validations": [],
            }
        contract["updated_at"] = now
        if path and tool in {"Read", "Edit", "Write"}:
            _bounded_unique(contract.setdefault("working_files", []), path, MAX_FILES)
        failures = contract.setdefault("failures", [])
        if command and failed:
            failures.append(
                {
                    "command": _redact(command, 180),
                    "status": "active",
                    "validation_kind": validation_kind,
                    "at": now,
                }
            )
            if len(failures) > MAX_FAILURES:
                del failures[: len(failures) - MAX_FAILURES]
        validations = contract.setdefault("validations", [])
        if validation_kind and command:
            status = "failed" if failed else "passed"
            validations.append(
                {
                    "kind": validation_kind,
                    "command": _redact(command, 180),
                    "status": status,
                    "at": now,
                }
            )
            if len(validations) > MAX_VALIDATIONS:
                del validations[: len(validations) - MAX_VALIDATIONS]
            if not failed:
                for failure in failures:
                    if (
                        isinstance(failure, dict)
                        and failure.get("status") == "active"
                        and failure.get("validation_kind") == validation_kind
                    ):
                        failure["status"] = "resolved"
                        failure["resolved_by"] = validation_kind
        session["contract"] = contract

    update_snapshot(root, mutate)


def _related_sessions(
    root: Path,
    *,
    selected: str | None,
    files: list[str],
    decisions: list[str],
    limit: int,
) -> list[str]:
    """Return older sessions linked by current files or explicit decisions."""
    sessions: list[str] = []
    queries = [*files[-3:], *decisions[-2:]]
    for query in queries:
        if not query:
            continue
        try:
            events = search_ledger(root, query, limit=max(4, limit))["events"]
        except (OSError, ValueError):
            continue
        for event in events:
            session = event.get("session")
            if not isinstance(session, str) or not session or session == selected:
                continue
            if session not in sessions:
                sessions.append(session)
            if len(sessions) >= 4:
                return sessions
    return sessions


def task_contract_context(
    root: Path,
    *,
    session_key: str | None,
    max_events: int = 6,
) -> str | None:
    """Render task state plus relevance-linked older session evidence."""
    snapshot = load_snapshot(root)
    sessions = snapshot.get("sessions")
    if not isinstance(sessions, dict):
        return None
    selected = session_key if session_key in sessions else snapshot.get("last_session")
    session = sessions.get(selected) if isinstance(selected, str) else None
    contract = session.get("contract") if isinstance(session, dict) else None
    if not isinstance(contract, dict):
        return None

    current_events = recent_ledger_events(
        root,
        session=selected if isinstance(selected, str) else None,
        kinds=("decision", "task_check"),
        limit=16,
    )
    decisions = [
        str(event["summary"])
        for event in reversed(current_events)
        if event.get("kind") == "decision"
    ][-4:]
    checks = [
        f"{event['summary']} [{event.get('status') or 'pending'}]"
        for event in reversed(current_events)
        if event.get("kind") == "task_check"
    ][-MAX_CHECKS:]
    files = [
        str(item)
        for item in contract.get("working_files", [])[-8:]
        if isinstance(item, str) and item
    ]

    lines = [
        "ACCO TASK CONTRACT - structured working state; repository remains authoritative.",
        f"Goal: {contract.get('goal') or 'coding task'}.",
        f"Task class: {contract.get('task_class') or 'general'}.",
    ]
    if decisions:
        lines.append("Decisions/constraints: " + "; ".join(decisions) + ".")
    if files:
        lines.append("Working files: " + ", ".join(files) + ".")

    active = [
        str(item.get("command"))
        for item in contract.get("failures", [])
        if isinstance(item, dict)
        and item.get("status") == "active"
        and item.get("command")
    ][-3:]
    if active:
        lines.append("Active failures: " + "; ".join(active) + ".")

    validations = [
        f"{item.get('kind')}={item.get('status')}"
        for item in contract.get("validations", [])[-4:]
        if isinstance(item, dict)
    ]
    if validations:
        lines.append("Validation state: " + ", ".join(validations) + ".")
    if checks:
        lines.append("Named checks: " + "; ".join(checks) + ".")

    relevant: list[dict] = []
    for related_session in _related_sessions(
        root,
        selected=selected if isinstance(selected, str) else None,
        files=files,
        decisions=decisions,
        limit=max_events,
    ):
        for event in recent_ledger_events(
            root,
            session=related_session,
            kinds=("decision", "file", "failure", "validation", "checkpoint"),
            limit=max_events,
        ):
            if event not in relevant:
                relevant.append(event)
            if len(relevant) >= max_events:
                break
        if len(relevant) >= max_events:
            break
    if relevant:
        lines.append("Relevant earlier project-session evidence:")
        for event in reversed(relevant[:max_events]):
            status = f" [{event.get('status')}]" if event.get("status") else ""
            lines.append(f"- {event.get('kind')}{status}: {event.get('summary')}")

    lines.append(
        "Verify live files/tests before relying on remembered state; resolved/stale "
        "history is orientation, not repository truth."
    )
    return "\n".join(lines)
