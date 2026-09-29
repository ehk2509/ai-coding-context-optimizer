"""Host-independent session continuity, exact deduplication, and waste signals."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shlex
import time

from ..estimate import estimate_tokens
from ..generation_policy import classify_output_task
from .ledger import append_ledger_event, decision_summaries, resume_ledger_context
from .task_contract import (
    task_contract_context,
    update_contract_from_prompt,
    update_contract_from_tool,
)
from .store import append_event, load_snapshot, update_snapshot

MAX_SESSIONS = 8
MAX_FILES = 12
MAX_COMMANDS = 10
MAX_FAILURES = 6
MAX_VALIDATIONS = 6
DEDUP_MIN_TOKENS = 120
TOOL_CASCADE_THRESHOLD = 12
REPEAT_COMMAND_THRESHOLD = 3
_SECRET_RE = re.compile(
    r"(?i)(?:(password|passwd|token|secret|api[_-]?key)\s*[=:]\s*)(\S+)"
)
_URL_CREDS_RE = re.compile(r"(https?://[^:/\s]+:)[^@/\s]+@")
_SECRET_FLAG_RE = re.compile(
    r"(?i)(--(?:password|passwd|token|secret|api[-_]?key|authorization)\s+)(\S+)"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)(authorization\s*:\s*)(?:bearer\s+)?(\S+)"
)


def _session_key(session_id: str | None) -> str:
    """Return an opaque stable key for one host session."""
    raw = session_id or "unknown"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _command_hash(command: str) -> str:
    """Return a stable digest for normalized command identity."""
    normalized = " ".join(command.split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _output_hash(text: str) -> str:
    """Return a stable digest for exact output identity."""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def _safe_command_label(command: str) -> str:
    """Return a bounded redacted command label safe for local persistence."""
    compact = " ".join(command.strip().split())

    def redact(match: re.Match[str]) -> str:
        """Replace a secret value while retaining its option/key name."""
        return match.group(0).replace(match.group(2), "<redacted>")

    compact = _SECRET_RE.sub(redact, compact)
    compact = _SECRET_FLAG_RE.sub(redact, compact)
    compact = _AUTH_HEADER_RE.sub(redact, compact)
    compact = _URL_CREDS_RE.sub(r"\1<redacted>@", compact)
    return compact[:180]


def _path_from_input(root: Path, tool_input: dict) -> str | None:
    """Return one repository-relative or absolute path from a tool input."""
    raw = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("filePath")
    )
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _bounded_append(items: list, value, limit: int) -> None:
    """Append one value while preserving only the newest bounded history."""
    items.append(value)
    if len(items) > limit:
        del items[: len(items) - limit]


def _session(payload: dict, key: str) -> dict:
    """Return or initialize one session record inside a project snapshot."""
    sessions = payload.setdefault("sessions", {})
    session = sessions.setdefault(
        key,
        {
            "task": "general",
            "turn": 0,
            "tool_count_turn": 0,
            "edits_turn": 0,
            "working_files": [],
            "commands": [],
            "failures": [],
            "validations": [],
            "output_cache": {},
            "signals_emitted": [],
        },
    )
    payload["last_session"] = key
    while len(sessions) > MAX_SESSIONS:
        oldest = next(iter(sessions))
        if oldest == key and len(sessions) > 1:
            oldest = next(item for item in sessions if item != key)
        sessions.pop(oldest, None)
    return session


def start_session(
    root: Path,
    *,
    session_id: str | None,
    source: str,
    enabled: bool = True,
) -> None:
    """Register a host session start without deleting cross-session continuity."""
    if not enabled:
        return
    key = _session_key(session_id)

    def mutate(payload: dict) -> None:
        """Refresh one session's ephemeral counters."""
        session = _session(payload, key)
        if source in {"startup", "clear", "compact", ""}:
            session["turn"] = 0
            session["tool_count_turn"] = 0
            session["edits_turn"] = 0
            session["signals_emitted"] = []
            if source == "clear":
                session["working_files"] = []
                session["commands"] = []
                session["failures"] = []
                session["validations"] = []
                session["output_cache"] = {}
        session["last_source"] = source
        session["last_activity"] = int(time.time())

    update_snapshot(root, mutate)
    append_ledger_event(
        root,
        kind="session",
        session=key,
        subject=source or "startup",
        summary=f"session start source={source or 'startup'}",
        status="started",
    )


def observe_prompt(
    root: Path,
    prompt: str,
    *,
    session_id: str | None,
    enabled: bool = True,
) -> None:
    """Record only prompt-derived task class; never persist prompt text."""
    if not enabled:
        return
    key = _session_key(session_id)
    task = classify_output_task(prompt) or None
    turn = 0

    def mutate(payload: dict) -> None:
        """Reset per-turn behavioral counters and retain task class only."""
        nonlocal turn
        session = _session(payload, key)
        session["turn"] = int(session.get("turn", 0)) + 1
        turn = int(session["turn"])
        session["tool_count_turn"] = 0
        session["edits_turn"] = 0
        session["signals_emitted"] = []
        if task:
            session["task"] = task
        session["last_activity"] = int(time.time())

    update_snapshot(root, mutate)
    append_ledger_event(
        root,
        kind="prompt",
        session=key,
        turn=turn,
        subject=task or "general",
        summary=f"turn {turn} task={task or 'general'}",
    )
    for decision in decision_summaries(prompt):
        append_ledger_event(
            root,
            kind="decision",
            session=key,
            turn=turn,
            subject="user-decision",
            summary=decision,
        )
    update_contract_from_prompt(
        root,
        key,
        prompt,
        task_class=task or "general",
    )


def deduplicate_output(
    root: Path,
    command: str,
    text: str,
    *,
    session_id: str | None,
    enabled: bool = True,
) -> str | None:
    """Collapse exact repeated command output to a compact deterministic stub."""
    if not enabled or not command.strip() or not text:
        return None
    tokens = estimate_tokens(text)
    if tokens < DEDUP_MIN_TOKENS:
        return None
    key = _session_key(session_id)
    command_id = _command_hash(command)
    digest = _output_hash(text)
    duplicate = False

    def mutate(payload: dict) -> None:
        """Compare and then refresh the bounded per-command output fingerprint."""
        nonlocal duplicate
        session = _session(payload, key)
        cache = session.setdefault("output_cache", {})
        previous = cache.get(command_id)
        if isinstance(previous, dict) and previous.get("digest") == digest:
            duplicate = True
        cache[command_id] = {
            "digest": digest,
            "tokens": tokens,
            "at": int(time.time()),
        }
        if len(cache) > 40:
            oldest = sorted(
                cache,
                key=lambda item: (
                    int(cache[item].get("at", 0))
                    if isinstance(cache[item], dict)
                    else 0
                ),
            )[:10]
            for item in oldest:
                cache.pop(item, None)

    update_snapshot(root, mutate)
    if not duplicate:
        return None
    label = _safe_command_label(command)
    stub = (
        "[acco cross-turn dedup: exact output unchanged from the prior "
        f"run of '{label}'; {tokens} estimated tokens omitted]\n"
    )
    return stub


def _validation_kind(command: str) -> str | None:
    """Classify common test, lint, typecheck, and build commands."""
    try:
        first = shlex.split(command)[:4]
    except ValueError:
        first = command.split()[:4]
    text = " ".join(first).lower()
    patterns = (
        (
            "test",
            (
                "pytest",
                "py.test",
                "jest",
                "vitest",
                "go test",
                "cargo test",
                "npm test",
                "pnpm test",
                "yarn test",
            ),
        ),
        ("lint", ("ruff", "eslint", "pylint", "clippy")),
        ("typecheck", ("tsc", "mypy", "pyright")),
        (
            "build",
            (
                "npm run build",
                "pnpm build",
                "yarn build",
                "cargo build",
                "go build",
                "gradle",
                "mvn",
            ),
        ),
    )
    for kind, needles in patterns:
        if any(needle in text for needle in needles):
            return kind
    return None


def _emit_once(
    root: Path,
    session: dict,
    *,
    signal_key: str,
    feature: str,
    note: str,
    session_key: str,
) -> str | None:
    """Emit one behavioral signal once per turn and append an audit event."""
    emitted = session.setdefault("signals_emitted", [])
    if signal_key in emitted:
        return None
    emitted.append(signal_key)
    append_event(
        root,
        {
            "kind": "waste",
            "feature": feature,
            "session": session_key,
        },
    )
    return note


def observe_tool(
    root: Path,
    payload: dict,
    *,
    original_text: str = "",
    delivered_text: str = "",
    failed: bool = False,
    enabled: bool = True,
    waste_detection: bool = True,
) -> str | None:
    """Track structured working state and return a rare bounded waste nudge."""
    if not enabled:
        return None
    key = _session_key(payload.get("session_id"))
    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    command = str(tool_input.get("command") or "") if tool == "Bash" else ""
    path = _path_from_input(root, tool_input)
    original_tokens = estimate_tokens(original_text) if original_text else 0
    delivered_tokens = estimate_tokens(delivered_text) if delivered_text else 0
    note: str | None = None
    current_turn = 0
    validation_kind: str | None = None
    command_label = ""

    def mutate(snapshot: dict) -> None:
        """Record one tool event and detect bounded repetitive behavior."""
        nonlocal note, current_turn, validation_kind, command_label
        session = _session(snapshot, key)
        current_turn = int(session.get("turn", 0))
        session["tool_count_turn"] = int(session.get("tool_count_turn", 0)) + 1
        session["last_activity"] = int(time.time())

        if path and tool in {"Read", "Edit", "Write"}:
            files = session.setdefault("working_files", [])
            files[:] = [item for item in files if item.get("path") != path]
            _bounded_append(
                files,
                {"path": path, "action": tool.lower(), "at": int(time.time())},
                MAX_FILES,
            )
        if tool in {"Edit", "Write"}:
            session["edits_turn"] = int(session.get("edits_turn", 0)) + 1

        if command:
            label = _safe_command_label(command)
            command_label = label
            command_id = _command_hash(command)
            output_id = _output_hash(original_text) if original_text else None
            commands = session.setdefault("commands", [])
            _bounded_append(
                commands,
                {
                    "id": command_id,
                    "label": label,
                    "failed": failed,
                    "output": output_id,
                    "at": int(time.time()),
                    "turn": int(session.get("turn", 0)),
                },
                MAX_COMMANDS,
            )
            if failed:
                failures = session.setdefault("failures", [])
                _bounded_append(
                    failures,
                    {
                        "label": label,
                        "output": output_id,
                        "at": int(time.time()),
                        "turn": int(session.get("turn", 0)),
                    },
                    MAX_FAILURES,
                )
            validation = _validation_kind(command)
            validation_kind = validation
            if validation:
                validations = session.setdefault("validations", [])
                _bounded_append(
                    validations,
                    {
                        "kind": validation,
                        "label": label,
                        "status": "failed" if failed else "passed",
                        "at": int(time.time()),
                    },
                    MAX_VALIDATIONS,
                )

            if waste_detection:
                current_turn = int(session.get("turn", 0))
                recent = [
                    item
                    for item in commands[-10:]
                    if item.get("turn") == current_turn
                ]
                repeats = sum(item.get("id") == command_id for item in recent)
                if repeats >= REPEAT_COMMAND_THRESHOLD:
                    note = _emit_once(
                        root,
                        session,
                        signal_key=f"repeat-command:{command_id}",
                        feature="repeated_command",
                        session_key=key,
                        note=(
                            "acco behavioral signal: the same command has "
                            "been run repeatedly this turn. Reuse prior evidence "
                            "or reassess what changed before running it again."
                        ),
                    )
                same_failures = [
                    item
                    for item in session.get("failures", [])
                    if item.get("turn") == current_turn
                    and item.get("label") == label
                    and output_id
                    and item.get("output") == output_id
                ]
                if len(same_failures) >= REPEAT_COMMAND_THRESHOLD:
                    note = _emit_once(
                        root,
                        session,
                        signal_key=f"retry-loop:{command_id}:{output_id}",
                        feature="retry_loop",
                        session_key=key,
                        note=(
                            "acco behavioral signal: the same failing "
                            "command returned the same output three times. Stop "
                            "blind retries and revisit the hypothesis."
                        ),
                    ) or note

        if waste_detection and (
            int(session.get("tool_count_turn", 0)) >= TOOL_CASCADE_THRESHOLD
            and int(session.get("edits_turn", 0)) == 0
        ):
            note = _emit_once(
                root,
                session,
                signal_key="tool-cascade",
                feature="tool_cascade",
                session_key=key,
                note=(
                    "acco behavioral signal: many tool calls occurred "
                    "this turn without an edit. Consolidate findings and choose "
                    "the next concrete action before expanding the search."
                ),
            ) or note

    update_snapshot(root, mutate)

    if path and tool in {"Read", "Edit", "Write"}:
        append_ledger_event(
            root,
            kind="file",
            session=key,
            turn=current_turn,
            subject=tool.lower(),
            path=path,
            status="failed" if failed else "ok",
            summary=f"{tool.lower()} {path}",
            metadata={"tool": tool},
        )
    if command and command_label:
        append_ledger_event(
            root,
            kind="command",
            session=key,
            turn=current_turn,
            subject="bash",
            status="failed" if failed else "passed",
            summary=command_label,
            metadata={
                "output_digest": _output_hash(original_text) if original_text else "",
                "original_tokens": original_tokens,
                "delivered_tokens": delivered_tokens,
            },
        )
        if failed:
            append_ledger_event(
                root,
                kind="failure",
                session=key,
                turn=current_turn,
                subject="command",
                status="failed",
                summary=command_label,
            )
        if validation_kind:
            append_ledger_event(
                root,
                kind="validation",
                session=key,
                turn=current_turn,
                subject=validation_kind,
                status="failed" if failed else "passed",
                summary=f"{validation_kind}: {command_label}",
            )

    update_contract_from_tool(
        root,
        key,
        tool=tool,
        path=path,
        command=command_label,
        failed=failed,
        validation_kind=validation_kind,
    )

    if original_tokens > delivered_tokens:
        feature = (
            "cross_turn_dedup"
            if delivered_text.startswith("[acco cross-turn dedup:")
            else "output_compression"
        )
        append_event(
            root,
            {
                "kind": "saving",
                "feature": feature,
                "estimated_tokens_saved": original_tokens - delivered_tokens,
                "session": key,
            },
        )
    return note


def continuity_context(
    root: Path,
    *,
    session_id: str | None,
    source: str,
    enabled: bool = True,
) -> str | None:
    """Render a compact structured checkpoint for resume or compaction."""
    if not enabled or source not in {"resume", "compact"}:
        return None

    # Prefer an explicit pre-compaction guardian snapshot when available. It is
    # captured before the host rewrites conversation state and therefore gives
    # a new/resumed host session a stable cold-resume packet.
    from .guardian import guardian_context

    guarded = guardian_context(
        root,
        session_id=session_id,
        source=source,
        enabled=enabled,
    )
    session_key = _session_key(session_id)
    contract = task_contract_context(
        root,
        session_key=session_key,
        max_events=6,
    )
    ledger = resume_ledger_context(
        root,
        session=session_key,
        limit=6,
    )
    if guarded:
        parts = [guarded]
        if contract:
            parts.append(contract)
        elif ledger:
            parts.append(ledger)
        return "\n\n".join(parts)
    snapshot = load_snapshot(root)
    sessions = snapshot.get("sessions")
    if not isinstance(sessions, dict) or not sessions:
        return None
    key = _session_key(session_id)
    session = sessions.get(key)
    if not isinstance(session, dict):
        last = snapshot.get("last_session")
        session = sessions.get(last) if isinstance(last, str) else None
    if not isinstance(session, dict):
        return None

    files = [
        str(item.get("path"))
        for item in session.get("working_files", [])[-8:]
        if isinstance(item, dict) and item.get("path")
    ]
    validations = [
        f"{item.get('kind')}={item.get('status')} ({item.get('label')})"
        for item in session.get("validations", [])[-4:]
        if isinstance(item, dict)
    ]
    failures = [
        str(item.get("label"))
        for item in session.get("failures", [])[-3:]
        if isinstance(item, dict) and item.get("label")
    ]
    commands = [
        str(item.get("label"))
        for item in session.get("commands", [])[-4:]
        if isinstance(item, dict) and item.get("label")
    ]
    if not any((files, validations, failures, commands)):
        return None

    lines = [
        "ACCO CONTINUITY CHECKPOINT — structured local state, not a transcript.",
        f"Task class: {session.get('task') or 'general'}.",
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
        "Treat this as orientation only: verify repository state before relying "
        "on any stale result."
    )
    append_event(
        root,
        {
            "kind": "continuity",
            "feature": "checkpoint_restore",
            "session": key,
        },
    )
    rendered = "\n".join(lines)
    if contract:
        return rendered + "\n\n" + contract
    return rendered + ("\n\n" + ledger if ledger else "")
