"""Render the self-contained Claude Code plugin directory for ACCO."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .lean_skill import SKILL_TEXT
import shutil
import tempfile

from . import __version__
from .state import state_dir

PLUGIN_NAME = "acco"
PLUGIN_SCHEMA = 1

_MANIFEST = {
    "name": PLUGIN_NAME,
    "displayName": "ACCO — AI Coding Context Optimizer",
    "description": (
        "Local context, output, session, retrieval, and prompt-ingress optimization "
        "for AI coding work."
    ),
    "author": {
        "name": "Elyes Hkiri",
        "url": "https://github.com/ehk2509",
    },
    "homepage": "https://github.com/ehk2509/ai-coding-context-optimizer",
    "repository": "https://github.com/ehk2509/ai-coding-context-optimizer",
    "license": "MIT",
}

_HOOKS = {
    "description": "ACCO context/output/session optimization hooks",
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Read|Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python -m acco.entry hook",
                        "timeout": 10,
                    }
                ],
            }
        ],
        "PostToolUse": [
            {
                "matcher": "Bash|Read|Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python -m acco.entry hook",
                        "timeout": 10,
                    }
                ],
            }
        ],
        "PreCompact": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "python -m acco.entry hook",
                        "timeout": 10,
                    }
                ]
            }
        ],
        "SessionStart": [
            {
                "matcher": "startup|resume|clear|compact",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python -m acco.entry hook",
                        "timeout": 10,
                    }
                ],
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "python -m acco.entry hook",
                        "timeout": 10,
                    }
                ]
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "python -m acco.entry hook",
                        "timeout": 10,
                    }
                ]
            }
        ],
        "StopFailure": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "python -m acco.entry hook",
                        "timeout": 10,
                    }
                ]
            }
        ],
    },
}

_MCP = {
    "acco": {
        "command": "python",
        "args": ["-m", "acco.entry", "serve", "."],
    }
}

_INGRESS_SKILL = r"""---
name: ingress
description: Resume an ACCO oversized prompt that was safely staged before model processing.
argument-hint: stage-id
allowed-tools: Bash
---

# Resume a staged ACCO prompt

The argument is an ACCO ingress stage id:

\`$ARGUMENTS\`

1. Run \`python -m acco.entry ingress-show "$ARGUMENTS" --path .\`.
2. Treat the returned staged packet as the user's request and continue the task.
3. If the packet contains an omitted line span and those exact bytes are needed,
   retrieve only the necessary range with:
   \`python -m acco.entry ingress-read "$ARGUMENTS" --path . --start-line N --end-line M\`.
4. Do not request the full original merely for convenience. The staged packet
   already includes exact head/tail evidence and explicit omitted-line locators.
5. Never infer or fabricate omitted content.
"""


def _target() -> Path:
    """Return the versioned local Claude plugin rendering directory."""
    safe_version = "".join(
        ch if ch.isalnum() or ch in ".-_" else "_"
        for ch in __version__
    )
    return state_dir() / "claude-plugin" / f"{PLUGIN_NAME}-{safe_version}"


def _write_json(path: Path, value: object) -> None:
    """Write stable UTF-8 JSON for one generated plugin asset."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_plugin() -> Path:
    """Render and return the absolute Claude Code plugin directory."""
    target = _target()
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(
        tempfile.mkdtemp(prefix=target.name + ".", dir=parent)
    )
    try:
        manifest = {**_MANIFEST, "version": __version__}
        _write_json(temporary / ".claude-plugin" / "plugin.json", manifest)
        _write_json(temporary / "hooks" / "hooks.json", _HOOKS)
        _write_json(temporary / ".mcp.json", _MCP)
        skill = temporary / "skills" / "ingress" / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(_INGRESS_SKILL, encoding="utf-8")
        lean_skill = temporary / "skills" / "acco-lean" / "SKILL.md"
        lean_skill.parent.mkdir(parents=True, exist_ok=True)
        lean_skill.write_text(SKILL_TEXT, encoding="utf-8")
        (temporary / ".acco-plugin.json").write_text(
            json.dumps(
                {
                    "schema": PLUGIN_SCHEMA,
                    "package_version": __version__,
                    "generated": True,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if target.exists():
            shutil.rmtree(target)
        os.replace(temporary, target)
        return target.resolve()
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def plugin_status() -> dict:
    """Return generated plugin metadata without mutating installation state."""
    target = _target()
    return {
        "schema": PLUGIN_SCHEMA,
        "version": __version__,
        "path": str(target.resolve()),
        "rendered": (target / ".claude-plugin" / "plugin.json").is_file(),
    }
