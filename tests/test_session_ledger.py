"""Tests for searchable persistent session history."""

from __future__ import annotations

from pathlib import Path

from acco.efficiency import (
    continuity_context,
    observe_prompt,
    observe_tool,
    search_ledger,
    start_session,
)
from acco.efficiency.ledger import (
    decision_summaries,
    ledger_path,
    recent_ledger_events,
)


def _root(tmp_path, monkeypatch) -> Path:
    """Create an isolated project and private ACCO state directory."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_session_ledger_records_structured_events_without_raw_outputs(
    tmp_path, monkeypatch
):
    """The searchable ledger should preserve work state, not transcript/tool bodies."""
    root = _root(tmp_path, monkeypatch)
    source = root / "src" / "auth.py"
    source.parent.mkdir()
    source.write_text("def refresh():\n    return True\n", encoding="utf-8")

    start_session(root, session_id="s1", source="startup")
    observe_prompt(
        root,
        "Use Redis for cache. password=super-secret. "
        "Investigate the refresh issue with customer Alice.",
        session_id="s1",
    )
    observe_tool(
        root,
        {
            "session_id": "s1",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(source)},
        },
    )
    observe_tool(
        root,
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "TOKEN=top-secret pytest tests/test_auth.py -q"},
        },
        original_text="FAILED very-private-stack-output\n",
        delivered_text="FAILED compact\n",
        failed=True,
    )

    events = recent_ledger_events(root, limit=20)
    serialized = ledger_path(root).read_bytes()

    assert any(event["kind"] == "decision" for event in events)
    assert any(event["kind"] == "file" and event["path"] == "src/auth.py" for event in events)
    assert any(event["kind"] == "failure" for event in events)
    assert any(event["kind"] == "validation" for event in events)
    assert b"very-private-stack-output" not in serialized
    assert b"top-secret" not in serialized
    assert b"super-secret" not in serialized
    assert b"<redacted>" in serialized


def test_decision_extraction_is_bounded_and_explicit():
    """Only explicit preference/decision sentences should become durable history."""
    prompt = (
        "The bug happens on Linux. "
        "Prefer SQLite for persistence. "
        "Use FTS5 for search. "
        "The customer name is Alice. "
        "Avoid storing raw prompts."
    )

    decisions = decision_summaries(prompt, limit=2)

    assert decisions == [
        "Prefer SQLite for persistence.",
        "Use FTS5 for search.",
    ]


def test_session_search_finds_older_decisions_and_commands(tmp_path, monkeypatch):
    """FTS/LIKE history search should surface relevant cross-turn state."""
    root = _root(tmp_path, monkeypatch)
    start_session(root, session_id="s1", source="startup")
    observe_prompt(root, "Prefer SQLite instead of JSON for the session ledger.", session_id="s1")
    observe_tool(
        root,
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/test_session_ledger.py -q"},
        },
        original_text="1 passed\n",
        delivered_text="1 passed\n",
    )

    found = search_ledger(root, "SQLite session ledger", limit=10)
    command = search_ledger(root, "pytest", kinds=["command"], limit=10)

    assert found["count"] >= 1
    assert any("SQLite" in event["summary"] for event in found["events"])
    assert command["count"] == 1
    assert "pytest tests/test_session_ledger.py -q" in command["events"][0]["summary"]


def test_resume_context_includes_searchable_ledger_history(tmp_path, monkeypatch):
    """Resume should augment the compact snapshot with recent durable event history."""
    root = _root(tmp_path, monkeypatch)
    start_session(root, session_id="s1", source="startup")
    observe_prompt(root, "Use the repository service instead of direct file access.", session_id="s1")
    observe_tool(
        root,
        {
            "session_id": "s1",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/service.py"},
        },
    )

    context = continuity_context(
        root,
        session_id="new-session",
        source="resume",
    )

    assert context is not None
    assert "ACCO SESSION LEDGER" in context
    assert "repository service" in context
    assert "src/service.py" in context
