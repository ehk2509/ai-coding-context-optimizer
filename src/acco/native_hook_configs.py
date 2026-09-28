"""Project-level native hook configuration for supported coding hosts.

Every mutation owns only ACCO hook entries. Shared settings files are merged
conservatively; Copilot uses a dedicated repository hook file so uninstall can
remove it without parsing unrelated user configuration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import update_json

ACCO_HOOK_PREFIX = "acco hook --host "
NATIVE_HOOK_HOSTS = ("cursor", "gemini", "qwen", "copilot")


def hook_command(host: str, event: str) -> str:
    """Return the stable ACCO command used by one native host event."""
    if host not in NATIVE_HOOK_HOSTS:
        raise ValueError(f"unsupported native hook host: {host}")
    return f"acco hook --host {host} --event {event}"


def cursor_hooks_path(root: Path) -> Path:
    """Return Cursor's project native-hook configuration path."""
    return root.resolve() / ".cursor" / "hooks.json"


def gemini_settings_path(root: Path) -> Path:
    """Return Gemini CLI's project settings path."""
    return root.resolve() / ".gemini" / "settings.json"


def qwen_settings_path(root: Path) -> Path:
    """Return Qwen Code's project settings path."""
    return root.resolve() / ".qwen" / "settings.json"


def copilot_hooks_path(root: Path) -> Path:
    """Return ACCO's owned Copilot repository-hook file."""
    return root.resolve() / ".github" / "hooks" / "acco.json"


def _is_acco_command(value: object, host: str) -> bool:
    """Return whether a hook command is an ACCO-owned native adapter."""
    return isinstance(value, str) and value.startswith(
        f"{ACCO_HOOK_PREFIX}{host} --event "
    )


def _cursor_entries() -> dict[str, list[dict[str, Any]]]:
    """Return ACCO's documented Cursor hook set."""
    return {
        "preToolUse": [
            {
                "command": hook_command("cursor", "preToolUse"),
                "matcher": "Shell|Read",
            }
        ],
        "beforeSubmitPrompt": [
            {"command": hook_command("cursor", "beforeSubmitPrompt")}
        ],
        "sessionStart": [
            {"command": hook_command("cursor", "sessionStart")}
        ],
        "preCompact": [
            {"command": hook_command("cursor", "preCompact")}
        ],
        "stop": [
            {"command": hook_command("cursor", "stop")}
        ],
    }


def _nested_entries(host: str) -> dict[str, list[dict[str, Any]]]:
    """Return Gemini/Qwen nested command-hook definitions."""
    if host == "gemini":
        specs = {
            "BeforeTool": ("^(read_file|run_shell_command)$",),
            "AfterTool": ("*",),
            "BeforeAgent": (None,),
            "SessionStart": ("*",),
            "PreCompress": ("*",),
            "AfterAgent": (None,),
        }
    elif host == "qwen":
        specs = {
            "PreToolUse": ("^(read_file|run_shell_command)$",),
            "UserPromptSubmit": (None,),
            "SessionStart": ("*",),
            "PreCompact": ("*",),
            "Stop": (None,),
            "StopFailure": (None,),
        }
    else:
        raise ValueError(host)

    result: dict[str, list[dict[str, Any]]] = {}
    for event, (matcher,) in specs.items():
        inner = {
            "type": "command",
            "command": hook_command(host, event),
            "name": f"acco-{event}",
            # Gemini CLI expresses command-hook timeout in milliseconds;
            # Qwen Code expresses it in seconds.
            "timeout": 10_000 if host == "gemini" else 10,
        }
        outer: dict[str, Any] = {"hooks": [inner]}
        if matcher is not None:
            outer["matcher"] = matcher
        result[event] = [outer]
    return result


def _remove_cursor_owned(payload: dict, host: str = "cursor") -> dict:
    """Remove ACCO-owned Cursor entries while preserving unrelated hooks."""
    updated = dict(payload)
    hooks = updated.get("hooks")
    if not isinstance(hooks, dict):
        return updated
    kept_hooks: dict[str, Any] = {}
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            kept_hooks[event] = entries
            continue
        kept = [
            item
            for item in entries
            if not (
                isinstance(item, dict)
                and _is_acco_command(item.get("command"), host)
            )
        ]
        if kept:
            kept_hooks[event] = kept
    if kept_hooks:
        updated["hooks"] = kept_hooks
    else:
        updated.pop("hooks", None)
    return updated


def install_cursor_hooks(root: Path) -> None:
    """Merge ACCO native hooks into Cursor project configuration."""
    path = cursor_hooks_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    def mutate(current: dict) -> dict:
        updated = _remove_cursor_owned(current)
        updated["version"] = updated.get("version", 1)
        hooks = dict(updated.get("hooks", {}))
        for event, entries in _cursor_entries().items():
            hooks.setdefault(event, [])
            if not isinstance(hooks[event], list):
                raise ValueError(f"Expected Cursor hooks.{event} to be an array")
            hooks[event] = [*hooks[event], *entries]
        updated["hooks"] = hooks
        return updated

    update_json(path, mutate)


def uninstall_cursor_hooks(root: Path) -> None:
    """Remove only ACCO native hooks from Cursor's shared hook file."""
    path = cursor_hooks_path(root)
    if path.exists():
        update_json(path, _remove_cursor_owned)


def _remove_nested_owned(payload: dict, host: str) -> dict:
    """Remove ACCO-owned Gemini/Qwen nested command hooks."""
    updated = dict(payload)
    hooks = updated.get("hooks")
    if not isinstance(hooks, dict):
        return updated
    kept_hooks: dict[str, Any] = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            kept_hooks[event] = groups
            continue
        kept_groups: list[Any] = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            inner = group.get("hooks")
            if not isinstance(inner, list):
                kept_groups.append(group)
                continue
            kept_inner = [
                item
                for item in inner
                if not (
                    isinstance(item, dict)
                    and _is_acco_command(item.get("command"), host)
                )
            ]
            if kept_inner:
                changed = dict(group)
                changed["hooks"] = kept_inner
                kept_groups.append(changed)
        if kept_groups:
            kept_hooks[event] = kept_groups
    if kept_hooks:
        updated["hooks"] = kept_hooks
    else:
        updated.pop("hooks", None)
    return updated


def _install_nested(root: Path, host: str, path: Path) -> None:
    """Install nested command hooks used by Gemini CLI or Qwen Code."""
    wanted = _nested_entries(host)
    path.parent.mkdir(parents=True, exist_ok=True)

    def mutate(current: dict) -> dict:
        updated = _remove_nested_owned(current, host)
        hooks = dict(updated.get("hooks", {}))
        for event, groups in wanted.items():
            hooks.setdefault(event, [])
            if not isinstance(hooks[event], list):
                raise ValueError(f"Expected {host} hooks.{event} to be an array")
            hooks[event] = [*hooks[event], *groups]
        updated["hooks"] = hooks
        return updated

    update_json(path, mutate)


def install_gemini_hooks(root: Path) -> None:
    """Install Gemini CLI project native hooks."""
    _install_nested(root, "gemini", gemini_settings_path(root))


def uninstall_gemini_hooks(root: Path) -> None:
    """Remove only ACCO hooks from Gemini CLI project settings."""
    path = gemini_settings_path(root)
    if path.exists():
        update_json(path, lambda current: _remove_nested_owned(current, "gemini"))


def install_qwen_hooks(root: Path) -> None:
    """Install Qwen Code project native hooks."""
    _install_nested(root, "qwen", qwen_settings_path(root))


def uninstall_qwen_hooks(root: Path) -> None:
    """Remove only ACCO hooks from Qwen Code project settings."""
    path = qwen_settings_path(root)
    if path.exists():
        update_json(path, lambda current: _remove_nested_owned(current, "qwen"))


def _copilot_payload() -> dict:
    """Return ACCO's dedicated cross-platform Copilot hook document."""
    def command(event: str, matcher: str | None = None) -> dict:
        item: dict[str, Any] = {
            "type": "command",
            "command": hook_command("copilot", event),
            "timeoutSec": 10,
        }
        if matcher:
            item["matcher"] = matcher
        return item

    return {
        "version": 1,
        "hooks": {
            "PreToolUse": [command("PreToolUse", "Bash|Read")],
            "PostToolUse": [command("PostToolUse")],
            "SessionStart": [command("SessionStart")],
            "PreCompact": [command("PreCompact")],
            "Stop": [command("Stop")],
        },
    }


def _copilot_owned(payload: object) -> bool:
    """Return whether a Copilot hook file consists entirely of ACCO entries."""
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return False
    hooks = payload.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        return False
    found = False
    for entries in hooks.values():
        if not isinstance(entries, list):
            return False
        for item in entries:
            if not isinstance(item, dict):
                return False
            if not _is_acco_command(item.get("command"), "copilot"):
                return False
            found = True
    return found


def validate_copilot_hooks_manageable(root: Path) -> None:
    """Refuse to overwrite a user-owned file at ACCO's Copilot hook path."""
    path = copilot_hooks_path(root)
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Refusing invalid Copilot hook JSON: {path}") from exc
    if not _copilot_owned(payload):
        raise ValueError(f"Refusing to replace unmanaged Copilot hook file: {path}")


def install_copilot_hooks(root: Path) -> None:
    """Write ACCO's dedicated repository-level Copilot hook file."""
    validate_copilot_hooks_manageable(root)
    path = copilot_hooks_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    update_json(path, lambda _current: _copilot_payload())


def uninstall_copilot_hooks(root: Path) -> None:
    """Delete ACCO's Copilot hook file only when it remains ACCO-owned."""
    path = copilot_hooks_path(root)
    if not path.exists():
        return
    validate_copilot_hooks_manageable(root)
    path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


def native_hooks_configured(root: Path, host: str) -> bool:
    """Return whether all ACCO native hook commands for a host are installed."""
    root = root.resolve()
    if host == "cursor":
        path = cursor_hooks_path(root)
        wanted = {
            command
            for entries in _cursor_entries().values()
            for item in entries
            if (command := item.get("command"))
        }
    elif host in {"gemini", "qwen"}:
        path = gemini_settings_path(root) if host == "gemini" else qwen_settings_path(root)
        wanted = {
            inner["command"]
            for groups in _nested_entries(host).values()
            for group in groups
            for inner in group["hooks"]
        }
    elif host == "copilot":
        path = copilot_hooks_path(root)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return _copilot_owned(payload) and payload == _copilot_payload()
    else:
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    seen: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            command = value.get("command")
            if isinstance(command, str) and _is_acco_command(command, host):
                seen.add(command)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return wanted <= seen
