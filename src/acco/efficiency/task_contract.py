"""Structured task contract and relevance-based session reconstruction."""

from __future__ import annotations

from pathlib import Path
import re
import time

from ..task_checklist import extract_task_checklist
from .ledger import decision_summaries, search_ledger
from .store import load_snapshot, update_snapshot

MAX_DECISIONS = 8
MAX_FILES = 16
MAX_FAILURES = 8
MAX_VALIDATIONS = 8
MAX_CHECKS = 8
_SECRET_RE = re.compile(
    r"(?i)(?:(password|passwd|token|secret|api[_-]?key)\\s*[=:]\\s*)(\\S+)"
)


def _redact(text: str, limit: int = 240) -> str:
    """Return bounded credential-redacted task state."""
    compact = " ".join(str(text).split())

    def replace(match: re.Match[str]) -> str:
        return match.group(0).replace(match.group(2), "<redacted>")

    return _SECRET_RE.sub(replace, compact)[:limit]


def _goal(prompt: str) -> str:
    """Extract one bounded prose goal, never the complete prompt."""
    without_fences = re.sub(r"\x60\x60\x60[\\s\\S]*?\x60\x60\x60", " ", prompt)
    pieces = [piece.strip() for piece in without_fences.splitlines() if piece.strip()]
    return _redact(pieces[0]) if pieces else "coding task"


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
    """Refresh structured task state from explicit prompt evidence."""
    decisions = decision_summaries(prompt, limit=MAX_DECISIONS)
    checks = extract_task_checklist(prompt)[:MAX_CHECKS]
    now = int(time.time())

    def mutate(snapshot: dict) -> None:
        sessions = snapshot.setdefault("sessions", {})
        session = sessions.setdefault(session_key, {})
        previous = session.get("contract")
        contract = previous if isinstance(previous, dict) else {}
        contract["goal"] = _goal(prompt)
        contract["task_class"] = task_class or "general"
        contract["updated_at"] = now
        contract.setdefault("created_at", now)
        contract.setdefault("decisions", [])
        contract.setdefault("working_files", [])
        contract.setdefault("failures", [])
        contract.setdefault("validations", [])
        contract.setdefault("checks", [])
        for decision in decisions:
            _bounded_unique(contract["decisions"], decision, MAX_DECISIONS)
        if checks:
            contract["checks"] = [
                {"item": _redact(item, 220), "status": "pending"}
                for item in checks
            ]
        session["contract"] = contract

    update_snapshot(root, mutate)


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
        sessions = snapshot.setdefault("sessions", {})
        session = sessions.setdefault(session_key, {})
        contract = session.get("contract")
        if not isinstance(contract, dict):
            contract = {
                "goal": "coding task",
                "task_class": str(session.get("task") or "general"),
                "created_at": now,
                "decisions": [],
                "working_files": [],
                "failures": [],
                "validations": [],
                "checks": [],
            }
        contract["updated_at"] = now
        if path and tool in {"Read", "Edit", "Write"}:
            _bounded_unique(contract.setdefault("working_files", []), path, MAX_FILES)
        failures = contract.setdefault("failures", [])
        if command and failed:
            failures.append({"command": _redact(command, 180), "status": "active", "at": now})
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
                    if isinstance(failure, dict) and failure.get("status") == "active":
                        failure["status"] = "resolved"
                        failure["resolved_by"] = validation_kind
                for check in contract.setdefault("checks", []):
                    if isinstance(check, dict) and check.get("status") == "pending":
                        check["status"] = "needs-explicit-check"
        session["contract"] = contract

    update_snapshot(root, mutate)


def task_contract_context(
    root: Path,
    *,
    session_key: str | None,
    max_events: int = 6,
) -> str | None:
    """Render task state plus relevance-ranked older session evidence."""
    snapshot = load_snapshot(root)
    sessions = snapshot.get("sessions")
    if not isinstance(sessions, dict):
        return None
    selected = session_key if session_key in sessions else snapshot.get("last_session")
    session = sessions.get(selected) if isinstance(selected, str) else None
    contract = session.get("contract") if isinstance(session, dict) else None
    if not isinstance(contract, dict):
        return None

    lines = [
        "ACCO TASK CONTRACT - structured working state; repository remains authoritative.",
        f"Goal: {contract.get('goal') or 'coding task'}.",
        f"Task class: {contract.get('task_class') or 'general'}.",
    ]
    decisions = [str(x) for x in contract.get("decisions", [])[-4:] if isinstance(x, str)]
    files = [str(x) for x in contract.get("working_files", [])[-8:] if isinstance(x, str)]
    if decisions:
        lines.append("Decisions/constraints: " + "; ".join(decisions) + ".")
    if files:
        lines.append("Working files: " + ", ".join(files) + ".")
    active = [
        str(x.get("command")) for x in contract.get("failures", [])
        if isinstance(x, dict) and x.get("status") == "active" and x.get("command")
    ][-3:]
    if active:
        lines.append("Active failures: " + "; ".join(active) + ".")
    validations = [
        f"{x.get('kind')}={x.get('status')}" for x in contract.get("validations", [])[-4:]
        if isinstance(x, dict)
    ]
    if validations:
        lines.append("Validation state: " + ", ".join(validations) + ".")
    checks = [
        f"{x.get('item')} [{x.get('status')}]" for x in contract.get("checks", [])
        if isinstance(x, dict) and x.get("item")
    ]
    if checks:
        lines.append("Named checks: " + "; ".join(checks) + ".")

    query = " ".join(
        [
            str(contract.get("goal") or ""),
            *decisions[-2:],
            *[Path(path).name for path in files[-3:]],
        ]
    ).strip()
    if query:
        try:
            related = search_ledger(root, query, limit=max(1, min(max_events, 12)))["events"]
        except (OSError, ValueError):
            related = []
        relevant = [
            event for event in related
            if event.get("session") != selected
            and event.get("kind") in {"decision", "file", "failure", "validation", "checkpoint"}
        ][:max_events]
        if relevant:
            lines.append("Relevant earlier project-session evidence:")
            for event in relevant:
                status = f" [{event.get('status')}]" if event.get("status") else ""
                lines.append(f"- {event.get('kind')}{status}: {event.get('summary')}")

    lines.append(
        "Verify live files/tests before relying on remembered state; resolved/stale "
        "history is orientation, not repository truth."
    )
    return "\n".join(lines)
