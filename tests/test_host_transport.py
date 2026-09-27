"""Tests for explicit coding-host provider transport capabilities."""

from __future__ import annotations

import json

from acco.command_handlers.host import transport_status_main
from acco.host_transport import (
    persistent_hosts,
    persistent_provider_map,
    transport_for,
)


def test_persistent_transport_registry_is_fail_closed():
    """Only hosts with ACCO-owned durable routing should be persistent."""
    assert persistent_hosts() == ("claude", "codex")
    assert persistent_provider_map() == {
        "claude": "anthropic",
        "codex": "openai",
    }


def test_transport_registry_distinguishes_foreground_manual_and_environment_only():
    """Capability records should explain why nonpersistent hosts are excluded."""
    assert transport_for("copilot").persistent == "environment-only"
    assert transport_for("openclaw").persistent == "environment-only"
    assert transport_for("cursor").persistent == "manual-setting"
    assert transport_for("cursor-agent").host == "cursor"
    assert transport_for("claude-code").persistent == "automatic"


def test_transport_status_json(capsys):
    """CLI should expose the registry without implying unsupported persistence."""
    assert transport_status_main(["--host", "cursor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["host"]["host"] == "cursor"
    assert payload["host"]["persistent"] == "manual-setting"
    assert "private" not in payload["host"]["persistent"]


def test_transport_status_unknown_host_fails_closed(capsys):
    """Unknown hosts should not be silently treated as generic persistent clients."""
    assert transport_status_main(["--host", "mystery-agent"]) == 2
    assert "unknown host transport" in capsys.readouterr().err
