"""SDK coverage for out-of-context execution."""

from __future__ import annotations

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
