"""Tests for the framework-neutral Python/HTTP SDK surfaces."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acco.sdk import AccoEngine
from acco.sdk_server import SdkApplication, SdkServerConfig


def _engine(tmp_path, monkeypatch, *, capacity=512 * 1024 * 1024):
    """Create one isolated SDK engine with private recovery state."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return AccoEngine(root, recovery_capacity_bytes=capacity)


def test_python_sdk_context_is_recoverable(tmp_path, monkeypatch):
    """Lossy context transforms must round-trip to the exact original bytes."""
    engine = _engine(tmp_path, monkeypatch)
    original = "\n".join(
        f"progress row {index} " + "x" * 80 for index in range(240)
    )

    result = engine.optimize_context(
        original,
        query="progress",
        command="custom-agent-tool",
        max_lines=24,
        min_reduction=0.0,
    )

    assert result["changed"] is True
    assert result["output_tokens"] < result["original_tokens"]
    assert result["recovery_handle"]
    recovered = engine.recover(result["recovery_handle"])
    assert recovered["encoding"] == "utf-8"
    assert recovered["payload"] == original


def test_python_sdk_provider_request_reuses_production_transform(
    tmp_path, monkeypatch
):
    """Custom agents should get the same provider transform and recovery contract."""
    engine = _engine(tmp_path, monkeypatch)
    noisy = "\n".join(
        f"build progress {index} " + "x" * 80 for index in range(180)
    )
    body = {
        "messages": [
            {"role": "tool", "content": noisy},
            {"role": "user", "content": "diagnose the build"},
        ]
    }

    result = engine.optimize_provider_request("anthropic", body)

    assert result["metadata"]["changed"] is True
    handles = result["metadata"]["recovery_handles"]
    assert handles
    assert engine.recover(handles[0])["payload"] == noisy


def test_python_sdk_output_recovery_fails_open_on_capacity(
    tmp_path, monkeypatch
):
    """Output middleware must return the original when exact recovery cannot fit."""
    engine = _engine(tmp_path, monkeypatch, capacity=8)
    original = "\n".join(f"ordinary output line {index}" for index in range(200))

    result = engine.optimize_output(
        original,
        command="custom command",
        max_lines=20,
        keep_tail=5,
        min_reduction=0.0,
    )

    assert result["changed"] is False
    assert result["text"] == original
    assert result["recovery_handle"] is None
    assert result["output_tokens"] == result["original_tokens"]


def test_python_middleware_binds_provider_and_tool_flow(tmp_path, monkeypatch):
    """The convenience facade should map agent lifecycle calls to one engine."""
    engine = _engine(tmp_path, monkeypatch)
    middleware = engine.middleware("openai")
    body = {"messages": [{"role": "user", "content": "hello"}]}

    request = middleware.before_request(
        body,
        compress_schemas=False,
        compress_tool_results=False,
        prefix_tracking=False,
    )
    tool = middleware.after_tool_result(
        "\n".join(f"row {index} " + "x" * 50 for index in range(160)),
        query="row 99",
        command="search",
        max_lines=20,
        min_reduction=0.0,
    )

    assert request["body"] == body
    assert request["metadata"]["changed"] is False
    assert tool["changed"] is True
    assert middleware.recover(tool["recovery_handle"])["payload"].startswith(
        "row 0"
    )


def test_sdk_application_dispatches_health_context_and_recovery(
    tmp_path, monkeypatch
):
    """The HTTP bridge application should expose stable versioned primitives."""
    engine = _engine(tmp_path, monkeypatch)
    app = SdkApplication(engine)

    status, health = app.dispatch("GET", "/v1/health")
    assert status == 200
    assert health["status"] == "ok"
    assert health["root"] == str(engine.root)

    original = "\n".join(f"result {index} " + "z" * 80 for index in range(180))
    status, optimized = app.dispatch(
        "POST",
        "/v1/context/optimize",
        {
            "text": original,
            "query": "result 120",
            "command": "tool",
            "options": {"max_lines": 20, "min_reduction": 0.0},
        },
    )
    assert status == 200
    assert optimized["changed"] is True

    status, recovered = app.dispatch(
        "POST",
        "/v1/recover",
        {"handle": optimized["recovery_handle"]},
    )
    assert status == 200
    assert recovered["payload"] == original


def test_python_sdk_browser_context_specializes_ax_payload(
    tmp_path, monkeypatch
):
    """Custom Python agents should get browser-specific context focusing."""
    engine = _engine(tmp_path, monkeypatch)
    snapshot = "\n".join(
        f'- link "Product {index}" [ref=e{index}]'
        for index in range(150)
    )

    result = engine.optimize_browser_context(
        snapshot,
        query="Product 123",
        max_lines=24,
        min_tokens=0,
    )

    assert result["kind"] == "ax"
    assert result["changed"] is True
    assert "Product 123" in result["text"]
    assert engine.recover(result["recovery_handle"])["payload"] == snapshot


def test_sdk_application_exposes_browser_optimization(
    tmp_path, monkeypatch
):
    """The local SDK bridge should expose browser specialization explicitly."""
    engine = _engine(tmp_path, monkeypatch)
    app = SdkApplication(engine)
    payload = {
        "snapshot": {
            "role": "main",
            "name": "Catalog",
            "children": [
                {"role": "button", "name": f"Buy {index}"}
                for index in range(120)
            ],
        }
    }
    text = json.dumps(payload)

    status, result = app.dispatch(
        "POST",
        "/v1/browser/optimize",
        {
            "text": text,
            "query": "Buy 88",
            "options": {
                "max_lines": 20,
                "min_tokens": 0,
                "format_hint": "auto",
            },
        },
    )

    assert status == 200
    assert result["kind"] == "json"
    assert result["changed"] is True
    assert "Buy 88" in result["text"]


def test_sdk_application_rejects_unknown_or_missing_recovery(
    tmp_path, monkeypatch
):
    """Transport errors should be explicit without exposing internals."""
    app = SdkApplication(_engine(tmp_path, monkeypatch))

    assert app.dispatch("GET", "/v1/nope")[0] == 405
    assert app.dispatch("POST", "/v1/nope", {}) == (404, {"error": "not_found"})
    status, missing = app.dispatch(
        "POST",
        "/v1/recover",
        {"handle": "tsr_" + "0" * 32},
    )
    assert status == 404
    assert missing["error"] == "recovery_not_found"


def test_sdk_server_defaults_to_loopback(tmp_path):
    """Non-loopback exposure must require an explicit operator override."""
    root = tmp_path / "repo"
    root.mkdir()

    safe = SdkServerConfig(root=root).validate()
    assert safe.bind == "127.0.0.1"

    with pytest.raises(ValueError, match="loopback"):
        SdkServerConfig(root=root, bind="0.0.0.0").validate()

    explicit = SdkServerConfig(
        root=root,
        bind="0.0.0.0",
        allow_non_loopback=True,
    ).validate()
    assert explicit.allow_non_loopback is True


def test_sdk_config_requires_existing_project_root(tmp_path):
    """Embedding against a nonexistent root should fail before creating state."""
    with pytest.raises(ValueError, match="existing directory"):
        AccoEngine(Path(tmp_path / "missing"))



def test_rag_middleware_focuses_documents_and_recovers_canonical_input(
    tmp_path, monkeypatch
):
    """RAG adapter should keep focused chunks without performing retrieval."""
    engine = _engine(tmp_path, monkeypatch)
    documents = [
        {
            "id": f"doc-{index}",
            "content": (
                f"general catalog text {index} " + "x" * 200
                if index != 17
                else "critical websocket retry policy " + "y" * 200
            ),
            "score": 1.0 - index / 100,
        }
        for index in range(30)
    ]

    result = engine.rag().optimize(
        documents,
        query="websocket retry",
        max_documents=5,
        min_reduction=0.0,
    )

    assert result["domain"] == "rag"
    assert result["changed"] is True
    assert result["metadata"]["documents"] == 30
    assert result["metadata"]["shown_documents"] == 5
    assert any(item["id"] == "doc-17" for item in result["value"])
    recovered = engine.rag().recover(result["recovery_handle"])
    assert json.loads(recovered["payload"]) == documents
    assert recovered["metadata"]["domain"] == "rag"
    assert recovered["metadata"]["representation"] == "canonical-json"


def test_api_middleware_compacts_large_json_without_network_side_effects(
    tmp_path, monkeypatch
):
    """API adapter should only transform caller-supplied JSON context."""
    engine = _engine(tmp_path, monkeypatch)
    payload = {
        "items": [
            {
                "id": index,
                "name": f"item-{index}",
                "status": "target" if index == 42 else "ordinary",
                "blob": "z" * 120,
            }
            for index in range(80)
        ],
        "cursor": "next-page",
    }

    result = engine.api().optimize(
        payload,
        query="target",
        min_reduction=0.0,
    )

    assert result["domain"] == "api"
    assert result["changed"] is True
    assert result["metadata"]["root_type"] == "object"
    rendered = json.dumps(result["value"])
    assert '"id": 42' in rendered
    assert len(result["value"]["items"]["items"]) <= 6
    recovered = engine.api().recover(result["recovery_handle"])
    assert json.loads(recovered["payload"]) == payload


def test_database_middleware_normalizes_positional_rows_and_focuses_matches(
    tmp_path, monkeypatch
):
    """Database adapter should compress supplied rows without executing SQL."""
    engine = _engine(tmp_path, monkeypatch)
    rows = [
        [index, f"user-{index}", "blocked" if index == 73 else "active"]
        for index in range(120)
    ]

    result = engine.database().optimize(
        rows,
        columns=["id", "name", "status"],
        query="blocked",
        max_rows=12,
        min_reduction=0.0,
    )

    assert result["domain"] == "database"
    assert result["changed"] is True
    assert result["metadata"]["rows"] == 120
    assert result["metadata"]["shown_rows"] == 12
    assert any(row["id"] == 73 for row in result["value"]["rows"])
    recovered = engine.database().recover(result["recovery_handle"])
    restored = json.loads(recovered["payload"])
    assert restored["columns"] == ["id", "name", "status"]
    assert restored["rows"][73] == [73, "user-73", "blocked"]


def test_domain_middleware_fails_open_when_recovery_capacity_is_unavailable(
    tmp_path, monkeypatch
):
    """Lossy structured middleware must return full input when recovery cannot fit."""
    engine = _engine(tmp_path, monkeypatch, capacity=8)
    payload = [{"id": index, "blob": "x" * 200} for index in range(50)]

    result = engine.optimize_api_payload(
        payload,
        min_reduction=0.0,
    )

    assert result["changed"] is False
    assert result["value"] == payload
    assert result["recovery_handle"] is None
    assert result["output_tokens"] == result["original_tokens"]


def test_database_middleware_rejects_ambiguous_or_non_json_rows(
    tmp_path, monkeypatch
):
    """Structured adapters should fail closed rather than stringify arbitrary objects."""
    engine = _engine(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="columns are required"):
        engine.optimize_database_rows([[1, "a"]])

    with pytest.raises(ValueError, match="strict JSON"):
        engine.optimize_api_payload({"bad": {1, 2, 3}})


def test_sdk_application_exposes_optional_domain_middleware(
    tmp_path, monkeypatch
):
    """The bridge should expose RAG/API/database adapters as opt-in endpoints."""
    app = SdkApplication(_engine(tmp_path, monkeypatch))

    status, rag = app.dispatch(
        "POST",
        "/v1/middleware/rag",
        {
            "documents": [
                {"id": index, "content": f"chunk {index} " + "x" * 80}
                for index in range(20)
            ],
            "query": "chunk 12",
            "options": {"max_documents": 4, "min_reduction": 0.0},
        },
    )
    assert status == 200
    assert rag["domain"] == "rag"
    assert rag["changed"] is True

    status, api = app.dispatch(
        "POST",
        "/v1/middleware/api",
        {
            "payload": {
                "items": [{"id": index, "blob": "x" * 80} for index in range(30)]
            },
            "options": {"min_reduction": 0.0},
        },
    )
    assert status == 200
    assert api["domain"] == "api"

    status, database = app.dispatch(
        "POST",
        "/v1/middleware/database",
        {
            "rows": [[index, f"name-{index}"] for index in range(40)],
            "columns": ["id", "name"],
            "options": {"max_rows": 10, "min_reduction": 0.0},
        },
    )
    assert status == 200
    assert database["domain"] == "database"



def test_python_sdk_exposes_context_budget_planner(tmp_path, monkeypatch):
    """Custom agents should receive the same whole-context allocation contract."""
    engine = _engine(tmp_path, monkeypatch)
    plan = engine.plan_context_budget(
        "Debug the failing authentication handler.",
        total_tokens=9000,
        observed_tokens={"tool_results": 2500, "schemas": 300},
    )

    assert plan["total_tokens"] == 9000
    assert plan["task"] == "debugging"
    assert sum(plan["allocations"].values()) == 9000
    assert plan["observed_tokens"]["tool_results"] == 2500


def test_sdk_application_exposes_context_budget_planner(tmp_path, monkeypatch):
    """The loopback bridge should expose whole-context planning to non-Python agents."""
    app = SdkApplication(_engine(tmp_path, monkeypatch))
    status, plan = app.dispatch(
        "POST",
        "/v1/context-budget",
        {
            "prompt": "Review the production authentication migration.",
            "total_tokens": 10000,
            "options": {
                "observed_tokens": {
                    "memory": 200,
                    "tool_results": 1200,
                }
            },
        },
    )

    assert status == 200
    assert plan["total_tokens"] == 10000
    assert plan["task"] == "review"
    assert plan["risk_level"] == "high"
    assert sum(plan["allocations"].values()) == 10000


def test_sdk_provider_optimization_can_apply_context_budget(tmp_path, monkeypatch):
    """Embedded provider middleware should accept the same optional total budget."""
    engine = _engine(tmp_path, monkeypatch)
    historical = "\n".join(
        f"failure row {index} " + "x" * 100
        for index in range(240)
    )
    body = {
        "messages": [
            {"role": "tool", "content": historical},
            {"role": "user", "content": "Debug this failure."},
        ]
    }

    result = engine.optimize_provider_request(
        "openai",
        body,
        compress_schemas=False,
        tool_result_min_tokens=100,
        prefix_tracking=False,
        context_budget_total_tokens=2000,
    )

    assert result["metadata"]["context_budget"]["total_tokens"] == 2000
    assert result["metadata"]["changed"] is True


def test_sdk_application_exposes_learned_runtime_reports(tmp_path, monkeypatch):
    """The loopback bridge should expose the same report surfaces as Python."""
    engine = _engine(tmp_path, monkeypatch)
    app = SdkApplication(engine)

    status, observability = app.dispatch(
        "POST",
        "/v1/observability",
        {"days": 3},
    )
    assert status == 200
    assert observability["window_days"] == 3

    status, ttl = app.dispatch("POST", "/v1/cache-ttl", {})
    assert status == 200
    assert ttl["estimates"] == []

    status, holdout = app.dispatch(
        "POST",
        "/v1/output-holdout",
        {"bootstrap_samples": 20},
    )
    assert status == 200
    assert holdout["measured_output_token_reduction"] is None

    status, fields = app.dispatch(
        "POST",
        "/v1/tool-fields",
        {"limit": 10},
    )
    assert status == 200
    assert fields["fields"] == []
