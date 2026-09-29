"""Tests for task-contract reconstruction over persisted session events."""

from acco.efficiency import continuity_context, observe_prompt, observe_tool, start_session
from acco.efficiency.store import load_snapshot


def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def _contract(root):
    snapshot = load_snapshot(root)
    session = snapshot["sessions"][snapshot["last_session"]]
    return session["contract"]


def test_task_contract_keeps_goal_decisions_files_and_named_checks(tmp_path, monkeypatch):
    """Prompt/tool evidence should become bounded structured task state."""
    root = _root(tmp_path, monkeypatch)
    start_session(root, session_id="s1", source="startup")
    observe_prompt(
        root,
        "Fix refresh handling. Prefer the repository service. "
        "The issue also reproduces with refreshSession().",
        session_id="s1",
    )
    observe_tool(
        root,
        {
            "session_id": "s1",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/session.py"},
        },
    )

    contract = _contract(root)

    assert contract["goal"] == "coding task"
    assert contract["decision_count"] >= 1
    assert "src/session.py" in contract["working_files"]
    snapshot_text = str(contract)
    assert "Fix refresh handling" not in snapshot_text
    assert "repository service" not in snapshot_text


def test_validation_only_resolves_failure_from_same_family(tmp_path, monkeypatch):
    """Passing lint must not erase an active failing-test state."""
    root = _root(tmp_path, monkeypatch)
    start_session(root, session_id="s1", source="startup")
    observe_prompt(root, "Fix the failing auth test.", session_id="s1")

    observe_tool(
        root,
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/test_auth.py -q"},
        },
        original_text="1 failed",
        delivered_text="1 failed",
        failed=True,
    )
    observe_tool(
        root,
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "ruff check src"},
        },
        original_text="All checks passed",
        delivered_text="All checks passed",
        failed=False,
    )

    contract = _contract(root)
    assert any(
        item["status"] == "active" and item["validation_kind"] == "test"
        for item in contract["failures"]
    )

    observe_tool(
        root,
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/test_auth.py -q"},
        },
        original_text="1 passed",
        delivered_text="1 passed",
        failed=False,
    )

    contract = _contract(root)
    assert all(item["status"] == "resolved" for item in contract["failures"])


def test_resume_contains_task_contract_and_older_relevant_history(tmp_path, monkeypatch):
    """Resume should reconstruct task state while leaving the raw transcript out."""
    root = _root(tmp_path, monkeypatch)
    start_session(root, session_id="old", source="startup")
    observe_prompt(
        root,
        "Prefer the repository service for refresh handling.",
        session_id="old",
    )
    observe_tool(
        root,
        {
            "session_id": "old",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/refresh.py"},
        },
    )

    start_session(root, session_id="current", source="startup")
    observe_prompt(
        root,
        "Fix refresh handling in src/refresh.py.",
        session_id="current",
    )

    context = continuity_context(
        root,
        session_id="current",
        source="resume",
    )

    assert context is not None
    assert "ACCO TASK CONTRACT" in context
    assert "Goal: coding task." in context
    assert "Relevant earlier project-session evidence" in context
    assert "repository service" in context
