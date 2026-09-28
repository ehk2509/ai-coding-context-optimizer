"""Tests for generated Claude Code plugin and marketplace packaging."""

from __future__ import annotations

import json
from pathlib import Path

from acco import __version__
from acco.claude_plugin import plugin_status, render_plugin


ROOT = Path(__file__).resolve().parents[1]


def test_rendered_plugin_contains_owned_hooks_mcp_and_ingress_skill(
    tmp_path,
    monkeypatch,
):
    """The generated plugin should be complete without depending on shell PATH."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))

    path = render_plugin()

    manifest = json.loads(
        (path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    hooks = json.loads((path / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    mcp = json.loads((path / ".mcp.json").read_text(encoding="utf-8"))
    skill = (path / "skills" / "ingress" / "SKILL.md").read_text(encoding="utf-8")
    lean = (path / "skills" / "acco-lean" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert manifest["name"] == "acco"
    assert manifest["version"] == __version__
    assert set(hooks["hooks"]) == {
        "PreToolUse",
        "PostToolUse",
        "PreCompact",
        "SessionStart",
        "UserPromptSubmit",
        "Stop",
        "StopFailure",
    }
    commands = [
        hook["command"]
        for entries in hooks["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    ]
    assert set(commands) == {"python -m acco.entry hook"}
    assert mcp["acco"]["command"] == "python"
    assert mcp["acco"]["args"][:3] == ["-m", "acco.entry", "serve"]
    assert "ingress-show" in skill
    assert "Never infer or fabricate omitted content" in skill
    assert "Never skip investigation or verification" in lean
    assert plugin_status()["rendered"] is True


def test_marketplace_uses_explicit_command_source_and_renderer():
    """Marketplace installs should use Claude's approved command-source flow."""
    marketplace = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    plugin = marketplace["plugins"][0]
    source = plugin["source"]

    assert marketplace["name"] == "acco-tools"
    assert plugin["name"] == "acco"
    assert source["source"] == "command"
    command = source["command"]
    assert f"acco>={__version__}" in command
    assert "pip install --user --quiet" in command
    assert "git+https://github.com/ehk2509/ai-coding-context-optimizer.git" in command
    assert "render_plugin" in command
    assert len(command) <= 500
    assert all(32 <= ord(character) <= 126 for character in command)
    assert "    " not in command
    assert source["timeout"] <= 600
