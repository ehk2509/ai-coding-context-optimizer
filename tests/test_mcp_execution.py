"""MCP integration tests for out-of-context execution."""

from __future__ import annotations

import json

from acco.mcp_server.protocol import McpProtocol


def test_mcp_execute_returns_small_analysis_not_source(tmp_path, monkeypatch):
    """The MCP surface should expose local computation without echoing large inputs."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "events.log").write_text(
        "\n".join(["ok"] * 500 + ["error"] * 25),
        encoding="utf-8",
    )
    protocol = McpProtocol(tmp_path, profile="context")

    response = protocol.call_tool(
        "execute",
        {
            "files": ["events.log"],
            "code": (
                'lines = data["events.log"].splitlines()\n'
                'result = {"total": len(lines), "errors": lines.count("error")}\n'
            ),
        },
    )
    payload = json.loads(response["content"][0]["text"])

    assert payload["result"] == {"total": 525, "errors": 25}
    assert payload["out_of_context"] is True
    assert "ok\nok" not in response["content"][0]["text"]


def test_mcp_execute_oversized_result_can_be_recovered(tmp_path, monkeypatch):
    """Execution result truncation should reuse ACCO's exact recovery contract."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "input.txt").write_text("x", encoding="utf-8")
    protocol = McpProtocol(tmp_path, profile="full")

    response = protocol.call_tool(
        "execute",
        {
            "files": ["input.txt"],
            "code": 'result = ["row-" + str(i) for i in range(1000)]',
            "max_result_bytes": 1024,
        },
    )
    payload = json.loads(response["content"][0]["text"])
    assert payload["truncated"] is True

    recovered = protocol.call_tool(
        "recover_context",
        {"handle": payload["recovery_handle"]},
    )
    recovered_payload = json.loads(recovered["content"][0]["text"])
    exact = json.loads(recovered_payload["payload"])
    assert exact[0] == "row-0"
    assert exact[-1] == "row-999"


def test_adaptive_discovery_selects_execution_for_data_heavy_task(tmp_path):
    """Adaptive MCP disclosure should reveal execution only when task terms justify it."""
    protocol = McpProtocol(tmp_path, profile="adaptive")

    protocol.call_tool(
        "discover_tools",
        {
            "query": "analyze these large JSON logs and aggregate error counts",
            "max_tools": 10,
        },
    )
    listed = protocol.handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )
    names = {tool["name"] for tool in listed["result"]["tools"]}

    assert "execute" in names
    assert len(names) <= 10


def test_mcp_execute_file_and_batch_execute(tmp_path, monkeypatch):
    """MCP should expose reusable scripts and bounded multi-job computation."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "values.txt").write_text("1\n2\n4\n", encoding="utf-8")
    (tmp_path / "count.py").write_text(
        'result = len(data["values.txt"].splitlines())\n',
        encoding="utf-8",
    )
    protocol = McpProtocol(tmp_path, profile="context")

    file_result = json.loads(
        protocol.call_tool(
            "execute_file",
            {
                "program_file": "count.py",
                "files": ["values.txt"],
            },
        )["content"][0]["text"]
    )
    batch_result = json.loads(
        protocol.call_tool(
            "batch_execute",
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
        )["content"][0]["text"]
    )

    assert file_result["result"] == 3
    assert file_result["program_file"] == "count.py"
    assert batch_result["results"][0]["result"] == 7


def test_mcp_session_search_reads_structured_history(tmp_path, monkeypatch):
    """MCP memory surface should retrieve ledger events, not transcript bodies."""
    from acco.efficiency import observe_prompt, start_session

    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    start_session(tmp_path, session_id="s1", source="startup")
    observe_prompt(
        tmp_path,
        "Prefer the repository service instead of direct reads.",
        session_id="s1",
    )
    protocol = McpProtocol(tmp_path, profile="memory")

    result = protocol.call_tool(
        "session_search",
        {"query": "repository service"},
    )
    payload = json.loads(result["content"][0]["text"])

    assert payload["count"] >= 1
    assert any("repository service" in event["summary"] for event in payload["events"])
