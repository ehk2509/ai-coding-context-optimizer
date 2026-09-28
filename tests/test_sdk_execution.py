"""SDK coverage for out-of-context execution."""

from __future__ import annotations

from acco.sdk import AccoEngine


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
