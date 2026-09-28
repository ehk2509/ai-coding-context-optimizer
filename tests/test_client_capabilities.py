"""Tests for conservative client capability declarations."""

from acco.client_capabilities import (
    capabilities_for,
    capability_report,
    feature_support,
)


def test_claude_code_declares_managed_hook_boundaries():
    """Claude Code should expose only the boundaries ACCO manages directly."""
    caps = capabilities_for("claude")
    assert caps.client == "claude-code"
    assert caps.guaranteed("pre_tool_intercept")
    assert caps.guaranteed("post_tool_replace")
    assert caps.level("model_route_execution") == "advisory"


def test_unknown_client_fails_conservatively():
    """An unregistered host must never inherit optimistic capabilities."""
    caps = capabilities_for("future-agent")
    assert caps.client == "future-agent"
    assert all(level == "unknown" for level in caps.capabilities.values())


def test_feature_support_distinguishes_guarantee_from_fallback():
    """Conditional host features should not be reported as guaranteed."""
    adaptive = feature_support("cursor", "adaptive-mcp")
    assert adaptive["guaranteed"] is False
    assert adaptive["available_with_fallback"] is True

    ingress = feature_support("cursor", "prompt-ingress")
    assert ingress["guaranteed"] is True
    assert ingress["available_with_fallback"] is True


def test_capability_report_contains_feature_prerequisites():
    """Per-client reports should expose the exact requirement evidence."""
    report = capability_report("claude-code")
    assert report["client"]["client"] == "claude-code"
    assert "adaptive-mcp" in report["features"]
    assert "dynamic_mcp_refresh" in report["features"]["adaptive-mcp"]["requirements"]


def test_extended_hosts_expose_mcp_without_inventing_hook_guarantees():
    """MCP-only hosts should remain conservative about lifecycle interception."""
    for name in ("opencode", "openclaw", "hermes", "antigravity"):
        caps = capabilities_for(name)
        assert caps.guaranteed("mcp")
        assert caps.level("pre_tool_intercept") == "unknown"
        assert caps.level("model_route_execution") == "advisory"


def test_native_hook_hosts_report_only_documented_replacement_strength():
    """Native adapters should distinguish full result rewrite from partial hooks."""
    assert capabilities_for("cursor").guaranteed("pre_tool_intercept")
    assert capabilities_for("cursor").level("post_tool_replace") == "conditional"
    assert capabilities_for("copilot").guaranteed("post_tool_replace")
    assert capabilities_for("gemini").guaranteed("post_tool_replace")
    assert capabilities_for("qwen").level("post_tool_replace") == "no"
    assert capabilities_for("qwen").level("prompt_ingress") == "conditional"


def test_extended_host_aliases_normalize_to_registry_entries():
    """Common product names should resolve to stable capability identifiers."""
    assert capabilities_for("OpenCode").client == "opencode"
    assert capabilities_for("OpenClaw").client == "openclaw"
    assert capabilities_for("Hermes-Agent").client == "hermes"
    assert capabilities_for("GitHub-Copilot").client == "copilot"
    assert capabilities_for("Google-Antigravity").client == "antigravity"
    assert capabilities_for("Qwen").client == "qwen-code"
