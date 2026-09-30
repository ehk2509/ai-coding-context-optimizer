"""Tests for content-free provider/framework observability."""

from acco.observability import (
    observability_report,
    prometheus_metrics,
    record_framework_operation,
    record_provider_request,
)


def _root(tmp_path, monkeypatch):
    """Create an isolated project and state root."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_observability_aggregates_provider_and_framework_metrics(tmp_path, monkeypatch):
    """Operational metrics should aggregate latency and token deltas without content."""
    root = _root(tmp_path, monkeypatch)

    record_provider_request(
        root,
        provider="anthropic",
        shape="anthropic-messages",
        model="claude-test",
        status=200,
        latency_ms=10,
        changed=True,
        original_tokens=1000,
        output_tokens=700,
        recovery_handles=1,
    )
    record_provider_request(
        root,
        provider="anthropic",
        shape="anthropic-messages",
        model="claude-test",
        status=500,
        latency_ms=30,
        changed=False,
        original_tokens=500,
        output_tokens=500,
        recovery_handles=0,
    )
    record_framework_operation(
        root,
        framework="langchain",
        operation="context.optimize",
        original_tokens=800,
        output_tokens=400,
        latency_ms=4,
        changed=True,
    )

    report = observability_report(root, days=1)
    provider = report["providers"]["anthropic"]
    framework = report["frameworks"]["langchain:context.optimize"]

    assert provider["calls"] == 2
    assert provider["transformed"] == 1
    assert provider["estimated_context_tokens_removed"] == 300
    assert provider["recovery_handles"] == 1
    assert provider["latency_ms_p95"] == 30
    assert provider["status_classes"] == {"2xx": 1, "5xx": 1}
    assert framework["calls"] == 1
    assert framework["estimated_context_tokens_removed"] == 400


def test_prometheus_metrics_are_content_free(tmp_path, monkeypatch):
    """Metric exposition should include bounded labels but never request text."""
    root = _root(tmp_path, monkeypatch)
    record_provider_request(
        root,
        provider="openai",
        shape="openai-responses",
        model="gpt-test",
        status=200,
        latency_ms=12.5,
        changed=True,
        original_tokens=900,
        output_tokens=600,
        recovery_handles=2,
    )

    metrics = prometheus_metrics(root, days=1)

    assert 'acco_provider_requests_total{provider="openai"} 1' in metrics
    assert 'acco_provider_context_tokens_removed_total{provider="openai"} 300' in metrics
    assert "gpt-test" not in metrics


def test_framework_failures_are_counted_separately(tmp_path, monkeypatch):
    """Framework operation failures should remain visible without payload logging."""
    root = _root(tmp_path, monkeypatch)
    record_framework_operation(
        root,
        framework="vercel-ai",
        operation="provider.optimize",
        original_tokens=100,
        output_tokens=100,
        latency_ms=1,
        changed=False,
        success=False,
    )

    report = observability_report(root, days=1)

    assert report["frameworks"]["vercel-ai:provider.optimize"]["failures"] == 1
