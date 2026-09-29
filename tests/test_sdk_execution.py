"""SDK coverage for out-of-context execution."""

from __future__ import annotations

from acco.efficiency import observe_prompt, start_session
from acco.sdk import AccoEngine
from acco.sdk_server import SdkApplication


def test_python_sdk_executes_repository_analysis_out_of_context(tmp_path, monkeypatch):
    """Custom agents should get the same restricted execution primitive as MCP."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    (root / "metrics.txt").write_text("3\n5\n7\n", encoding="utf-8")
    engine = AccoEngine(root)

    result = engine.execute(
        'values = [int(v) for v in data["metrics.txt"].splitlines()]\n'
        'result = {"sum": sum(values), "count": len(values)}',
        ["metrics.txt"],
    )

    assert result["result"] == {"sum": 15, "count": 3}
    assert result["out_of_context"] is True


def test_sdk_bridge_dispatches_execution(tmp_path, monkeypatch):
    """Non-Python clients should reach the same engine through /v1/execute."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    (root / "values.txt").write_text("2\n4\n8\n", encoding="utf-8")
    app = SdkApplication(AccoEngine(root))

    status, result = app.dispatch(
        "POST",
        "/v1/execute",
        {
            "code": (
                'values = [int(v) for v in data["values.txt"].splitlines()]\n'
                'result = {"max": max(values)}'
            ),
            "files": ["values.txt"],
        },
    )

    assert status == 200
    assert result["result"] == {"max": 8}


def test_python_sdk_exposes_execute_file_and_batch(tmp_path, monkeypatch):
    """Custom agents should get reusable scripts and bounded batch execution."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    (root / "values.txt").write_text("1\n2\n3\n", encoding="utf-8")
    (root / "count.py").write_text(
        'result = len(data["values.txt"].splitlines())\n',
        encoding="utf-8",
    )
    engine = AccoEngine(root)

    file_result = engine.execute_file("count.py", ["values.txt"])
    batch_result = engine.batch_execute(
        [
            {
                "id": "sum",
                "code": (
                    'result = sum(int(v) for v in '
                    'data["values.txt"].splitlines())'
                ),
                "files": ["values.txt"],
            }
        ]
    )

    assert file_result["result"] == 3
    assert file_result["program_file"] == "count.py"
    assert batch_result["results"][0]["result"] == 6


def test_sdk_bridge_exposes_execution_and_session_ledger(tmp_path, monkeypatch):
    """Loopback clients should reach all new execution and history surfaces."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    (root / "values.txt").write_text("4\n6\n", encoding="utf-8")
    (root / "count.py").write_text(
        'result = len(data["values.txt"].splitlines())\n',
        encoding="utf-8",
    )
    start_session(root, session_id="s1", source="startup")
    observe_prompt(root, "Prefer FTS5 for session history.", session_id="s1")
    app = SdkApplication(AccoEngine(root))

    status, file_result = app.dispatch(
        "POST",
        "/v1/execute-file",
        {
            "program_file": "count.py",
            "files": ["values.txt"],
        },
    )
    assert status == 200
    assert file_result["result"] == 2

    status, batch_result = app.dispatch(
        "POST",
        "/v1/batch-execute",
        {
            "jobs": [
                {
                    "id": "sum",
                    "code": (
                        'result = sum(int(v) for v in '
                        'data["values.txt"].splitlines())'
                    ),
                    "files": ["values.txt"],
                }
            ]
        },
    )
    assert status == 200
    assert batch_result["results"][0]["result"] == 10

    status, history = app.dispatch(
        "POST",
        "/v1/session/search",
        {"query": "FTS5 history"},
    )
    assert status == 200
    assert history["count"] >= 1

    status, recent = app.dispatch(
        "POST",
        "/v1/session/recent",
        {"limit": 5},
    )
    assert status == 200
    assert recent["count"] >= 1
