"""Tests for idempotent, ownership-safe native hook configuration."""

from __future__ import annotations

import json

import pytest

from acco.native_hook_configs import (
    copilot_hooks_path,
    cursor_hooks_path,
    gemini_settings_path,
    install_copilot_hooks,
    install_cursor_hooks,
    install_gemini_hooks,
    install_qwen_hooks,
    native_hooks_configured,
    qwen_settings_path,
    uninstall_copilot_hooks,
    uninstall_cursor_hooks,
    uninstall_gemini_hooks,
    uninstall_qwen_hooks,
)


def test_cursor_hook_install_is_idempotent_and_preserves_user_entries(tmp_path):
    """Cursor setup should own only ACCO commands in the shared hooks file."""
    path = cursor_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "preToolUse": [
                        {"command": "./user-check.sh", "matcher": "Shell"}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    install_cursor_hooks(tmp_path)
    install_cursor_hooks(tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    commands = [
        item["command"]
        for item in payload["hooks"]["preToolUse"]
    ]
    assert commands.count("./user-check.sh") == 1
    assert commands.count(
        "acco hook --host cursor --event preToolUse"
    ) == 1
    assert native_hooks_configured(tmp_path, "cursor") is True

    uninstall_cursor_hooks(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["hooks"]["preToolUse"] == [
        {"command": "./user-check.sh", "matcher": "Shell"}
    ]


@pytest.mark.parametrize(
    "host,path_fn,install,uninstall,event",
    [
        (
            "gemini",
            gemini_settings_path,
            install_gemini_hooks,
            uninstall_gemini_hooks,
            "BeforeTool",
        ),
        (
            "qwen",
            qwen_settings_path,
            install_qwen_hooks,
            uninstall_qwen_hooks,
            "PreToolUse",
        ),
    ],
)
def test_nested_host_hooks_preserve_unrelated_settings(
    tmp_path, host, path_fn, install, uninstall, event
):
    """Gemini/Qwen nested hook setup should merge rather than replace settings."""
    path = path_fn(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "theme": "dark",
                "hooks": {
                    event: [
                        {
                            "matcher": "custom",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "./user-hook.sh",
                                }
                            ],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    install(tmp_path)
    install(tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["theme"] == "dark"
    assert native_hooks_configured(tmp_path, host) is True
    serialized = json.dumps(payload)
    assert serialized.count(f"acco hook --host {host} --event {event}") == 1
    assert serialized.count("./user-hook.sh") == 1

    uninstall(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload)
    assert "./user-hook.sh" in serialized
    assert f"acco hook --host {host}" not in serialized


def test_copilot_uses_owned_repository_hook_file(tmp_path):
    """Copilot hook install/uninstall should be exact and reversible."""
    install_copilot_hooks(tmp_path)
    path = copilot_hooks_path(tmp_path)
    first = path.read_text(encoding="utf-8")

    install_copilot_hooks(tmp_path)

    assert path.read_text(encoding="utf-8") == first
    assert native_hooks_configured(tmp_path, "copilot") is True

    uninstall_copilot_hooks(tmp_path)
    assert not path.exists()


def test_copilot_refuses_to_overwrite_user_owned_same_path(tmp_path):
    """A user-owned .github/hooks/acco.json must fail closed."""
    path = copilot_hooks_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "preToolUse": [
                        {
                            "type": "command",
                            "command": "./user-policy.sh",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unmanaged Copilot hook file"):
        install_copilot_hooks(tmp_path)

    assert "./user-policy.sh" in path.read_text(encoding="utf-8")


def test_gemini_and_qwen_timeout_units_follow_host_contracts(tmp_path):
    """Gemini uses milliseconds while Qwen command hooks use seconds."""
    install_gemini_hooks(tmp_path)
    install_qwen_hooks(tmp_path)

    gemini = json.loads(gemini_settings_path(tmp_path).read_text(encoding="utf-8"))
    qwen = json.loads(qwen_settings_path(tmp_path).read_text(encoding="utf-8"))

    gemini_timeout = gemini["hooks"]["BeforeTool"][0]["hooks"][0]["timeout"]
    qwen_timeout = qwen["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"]

    assert gemini_timeout == 10_000
    assert qwen_timeout == 10
