"""Integration-setup coverage for project-native host hooks."""

from __future__ import annotations

import json

from acco.integration_setup import (
    detect_hosts,
    setup_integrations,
    uninstall_integrations,
)
from acco.native_hook_configs import (
    cursor_hooks_path,
    gemini_settings_path,
    native_hooks_configured,
    qwen_settings_path,
)


def _which(names):
    """Return a deterministic executable detector."""
    return lambda name: f"/usr/bin/{name}" if name in names else None


def test_setup_installs_cursor_mcp_and_native_hooks_together(tmp_path):
    """Cursor readiness should require both MCP and project hook surfaces."""
    root = tmp_path / "repo"
    root.mkdir()

    result = setup_integrations(
        root,
        ("cursor",),
        which=_which({"cursor"}),
    )

    assert result["configured_hosts"] == ["cursor"]
    assert native_hooks_configured(root, "cursor")
    hooks = json.loads(cursor_hooks_path(root).read_text(encoding="utf-8"))
    assert "preToolUse" in hooks["hooks"]
    status = {item.name: item for item in detect_hosts(
        root,
        which=_which({"cursor"}),
    )}["cursor"]
    assert status.configured is True
    assert "native-hooks" in status.details

    uninstall_integrations(
        root,
        ("cursor",),
        which=_which({"cursor"}),
    )
    assert native_hooks_configured(root, "cursor") is False


def test_setup_supports_gemini_and_qwen_native_hooks(tmp_path):
    """Gemini/Qwen should become first-class setup targets without fake MCP claims."""
    root = tmp_path / "repo"
    root.mkdir()

    result = setup_integrations(
        root,
        ("gemini", "qwen"),
        which=_which({"gemini", "qwen"}),
    )

    assert result["configured_hosts"] == ["gemini", "qwen"]
    assert native_hooks_configured(root, "gemini")
    assert native_hooks_configured(root, "qwen")
    assert gemini_settings_path(root).is_file()
    assert qwen_settings_path(root).is_file()

    statuses = {
        item.name: item
        for item in detect_hosts(
            root,
            which=_which({"gemini", "qwen"}),
        )
    }
    assert statuses["gemini"].configured is True
    assert statuses["qwen"].configured is True
    assert statuses["gemini"].details == ("native-hooks", "project-local")
    assert statuses["qwen"].details == ("native-hooks", "project-local")

    uninstall_integrations(
        root,
        ("gemini", "qwen"),
        which=_which({"gemini", "qwen"}),
    )
    assert native_hooks_configured(root, "gemini") is False
    assert native_hooks_configured(root, "qwen") is False


def test_setup_all_detects_new_native_hook_hosts(tmp_path):
    """The all selector should include Gemini/Qwen when their CLIs are present."""
    root = tmp_path / "repo"
    root.mkdir()

    result = setup_integrations(
        root,
        ("all",),
        which=_which({"gemini", "qwen"}),
    )

    assert result["requested_hosts"] == ["gemini", "qwen"]
    assert result["configured_hosts"] == ["gemini", "qwen"]
