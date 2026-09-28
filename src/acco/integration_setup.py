"""Unified setup, detection, doctor, and uninstall for coding-agent integrations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import tempfile

from .config import update_json
from .install import HOOK_COMMAND, HOOK_MATCHERS, install as install_claude_hooks
from .install import settings_path as claude_settings_path
from .install import uninstall as uninstall_claude_hooks
from .lean_skill import (
    SKILL_TEXT as LEAN_SKILL_TEXT,
    install_lean_skill,
    skill_path as lean_skill_path,
)
from .host_configs import (
    RunCommand,
    antigravity_configured,
    antigravity_global_mcp_path,
    antigravity_mcp_path,
    copilot_cli_config_path,
    copilot_cli_configured,
    copilot_configured,
    copilot_mcp_path,
    copilot_vscode_configured,
    hermes_config_path,
    hermes_configured,
    install_antigravity,
    install_copilot_cli,
    install_copilot_vscode,
    install_hermes,
    install_openclaw,
    install_opencode,
    openclaw_config_path,
    openclaw_configured,
    opencode_configured,
    opencode_mcp_path,
    run_command,
    uninstall_antigravity,
    uninstall_copilot_cli,
    uninstall_copilot_vscode,
    uninstall_hermes,
    uninstall_openclaw,
    uninstall_opencode,
    validate_copilot_cli_manageable,
    validate_hermes_manageable,
    validate_opencode_manageable,
)
from .native_hook_configs import (
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
    validate_copilot_hooks_manageable,
)
from .policy import SKILL_TEXT
from .repository_service import RepositoryContextService
from .runtime_config import CONFIG_NAME, find_project_config, settings_for
from .sessions import transcript_paths

HOSTS = (
    "claude",
    "cursor",
    "codex",
    "opencode",
    "openclaw",
    "hermes",
    "copilot",
    "antigravity",
    "gemini",
    "qwen",
)
HOST_EXECUTABLES = {
    "claude": "claude",
    "cursor": "cursor",
    "codex": "codex",
    "opencode": "opencode",
    "openclaw": "openclaw",
    "hermes": "hermes",
    "copilot": "copilot",
    "antigravity": "agy",
    "gemini": "gemini",
    "qwen": "qwen",
}
CODEX_START = "# >>> acco managed >>>"
CODEX_END = "# <<< acco managed <<<"

DEFAULT_CONFIG = """version = 1

[profile]
mode = "safe"

[hooks]
guard = true
read_max_lines = 220
reread = false
delta = false
min_lines = 40
keep_tail = 15
allow = []

[output]
enabled = true
mode = "normal"
task = "auto"
adaptive = true
calibration_file = ".acco.output-calibration.json"
telemetry = true

[model_routing]
enabled = false
mode = "advisory"
current_model = ""
allowed_models = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"]
min_savings = 0.05
conservative = true
calibration_file = ".acco.routing-calibration.json"

[efficiency]
enabled = true
continuity = true
dedup = true
waste_detection = true
knowledge_read_avoidance = false
cache_economics = false
cache_expected_reuses = 2
cache_write_factor = 1.25
cache_read_factor = 0.10
cache_min_relative_savings = 0.05

[ingress]
enabled = false
threshold_tokens = 12000
packet_tokens = 1600

[retrieval]
cache = true
cache_max_entries = 64

[mcp]
profile = "full"
adaptive_max_tools = 12
compress_schemas = false

[provider]
prefix_tracking = true
history_dedup = true
model_routing = "off"
routing_calibration_file = ".acco.routing-calibration.json"
routing_min_savings = 0.05

[context_budget]
enabled = false
total_tokens = 12000

[tool_proxy]
enabled = false
provider = "ollama"
model = "qwen2.5-coder:7b"
endpoint = "http://127.0.0.1:11434"
min_tokens = 2500
target_tokens = 1800
model_input_tokens = 12000
timeout_seconds = 6.0
max_ranges = 4
max_range_lines = 80
"""


@dataclass(frozen=True)
class HostStatus:
    """Installation/configuration state for one supported host."""

    name: str
    detected: bool
    configured: bool
    executable: str | None
    config_paths: tuple[str, ...]
    details: tuple[str, ...] = ()


def _atomic_write(path: Path, text: str) -> None:
    """Atomically replace one UTF-8 text file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _mcp_entry(root: Path) -> dict:
    """Return the project-scoped MCP server definition."""
    return {"command": "acco", "args": ["serve", str(root.resolve())]}


def _merge_mcp(root: Path) -> Callable[[dict], dict]:
    """Return a JSON mutator that owns only the ACCO MCP entry."""
    def mutate(current: dict) -> dict:
        updated = dict(current)
        servers = dict(updated.get("mcpServers", {}))
        servers["acco"] = _mcp_entry(root)
        updated["mcpServers"] = servers
        return updated

    return mutate


def _remove_mcp(current: dict) -> dict:
    """Remove only the ACCO MCP entry from a JSON config."""
    updated = dict(current)
    servers = updated.get("mcpServers")
    if not isinstance(servers, dict):
        return updated
    servers = dict(servers)
    servers.pop("acco", None)
    if servers:
        updated["mcpServers"] = servers
    else:
        updated.pop("mcpServers", None)
    return updated


def _validate_json_object(path: Path) -> None:
    """Reject unreadable/non-object JSON before any multi-host setup mutation."""
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Refusing to overwrite invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")


def _validate_codex_manageable(path: Path) -> None:
    """Reject a conflicting unmanaged Codex ACCO section."""
    if not path.exists():
        return
    existing = path.read_text(encoding="utf-8")
    if "[mcp_servers.acco]" in existing and CODEX_START not in existing:
        raise ValueError(
            f"Refusing to replace unmanaged ACCO Codex config: {path}"
        )
    if CODEX_START in existing and CODEX_END not in existing:
        raise ValueError("Codex ACCO managed block is incomplete")


def _json_mcp_configured(path: Path) -> bool:
    """Return whether a JSON config contains ACCO MCP."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    servers = payload.get("mcpServers") if isinstance(payload, dict) else None
    return isinstance(servers, dict) and "acco" in servers


def claude_mcp_path(root: Path) -> Path:
    """Return Claude Code project MCP configuration path."""
    return root / ".mcp.json"


def cursor_mcp_path(root: Path) -> Path:
    """Return Cursor project MCP configuration path."""
    return root / ".cursor" / "mcp.json"


def codex_config_path(home: Path | None = None) -> Path:
    """Return Codex user configuration path."""
    return (home or Path.home()) / ".codex" / "config.toml"


def _codex_block() -> str:
    """Return the managed Codex MCP configuration block."""
    return (
        f"{CODEX_START}\n"
        "[mcp_servers.acco]\n"
        'command = "acco"\n'
        'args = ["serve", "."]\n'
        f"{CODEX_END}\n"
    )


def _strip_codex_block(text: str) -> str:
    """Remove the ACCO managed block while preserving all other TOML."""
    start = text.find(CODEX_START)
    if start < 0:
        return text
    end = text.find(CODEX_END, start)
    if end < 0:
        raise ValueError("Codex ACCO managed block is incomplete")
    end += len(CODEX_END)
    while end < len(text) and text[end] in "\r\n":
        end += 1
    return (text[:start].rstrip() + "\n" + text[end:].lstrip()).lstrip("\n")


def _install_codex(path: Path) -> None:
    """Install or refresh the marked Codex MCP block."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    _validate_codex_manageable(path)
    cleaned = _strip_codex_block(existing).rstrip()
    text = (cleaned + "\n\n" if cleaned else "") + _codex_block()
    _atomic_write(path, text)


def _uninstall_codex(path: Path) -> None:
    """Remove the marked Codex MCP block only."""
    if not path.exists():
        return
    existing = path.read_text(encoding="utf-8")
    cleaned = _strip_codex_block(existing)
    if cleaned == existing:
        return
    _atomic_write(path, cleaned)


def _ensure_managed_lean_skill(root: Path) -> str | None:
    """Install ACCO Lean for Claude without overwriting user-modified content."""
    path = lean_skill_path(root, "claude")
    if path.exists():
        try:
            if path.read_text(encoding="utf-8") != LEAN_SKILL_TEXT:
                return None
        except OSError:
            return None
    installed = install_lean_skill(root, host="claude")
    return str(installed[0]) if installed else None


def _remove_managed_lean_skill(root: Path) -> None:
    """Remove the ACCO Lean skill only while it still matches our template."""
    path = lean_skill_path(root, "claude")
    if not path.exists():
        return
    try:
        current = path.read_text(encoding="utf-8")
    except OSError:
        return
    if current != LEAN_SKILL_TEXT:
        return
    path.unlink()
    for directory in (path.parent, path.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            break


def _remove_managed_claude_skill(root: Path) -> None:
    """Remove the generated Claude skill only when it still matches our template."""
    path = root / ".claude" / "skills" / "token-budget" / "SKILL.md"
    if not path.exists():
        return
    try:
        current = path.read_text(encoding="utf-8")
    except OSError:
        return
    if current != SKILL_TEXT:
        return
    path.unlink()
    for directory in (path.parent, path.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            break


def _claude_hooks_configured(root: Path) -> bool:
    """Return whether project Claude settings contain ACCO hooks."""
    path = claude_settings_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    hooks = payload.get("hooks") if isinstance(payload, dict) else None
    if not isinstance(hooks, dict):
        return False
    configured_events: set[str] = set()
    for event, entries in hooks.items():
        if event not in HOOK_MATCHERS or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for command in entry.get("hooks", []):
                if isinstance(command, dict) and command.get("command") == HOOK_COMMAND:
                    configured_events.add(event)
                    break
    return configured_events == set(HOOK_MATCHERS)



def _copilot_vscode_installed(home: Path) -> bool:
    """Return whether a VS Code GitHub Copilot extension is installed."""
    extensions = home / ".vscode" / "extensions"
    if not extensions.is_dir():
        return False
    return bool(
        any(extensions.glob("github.copilot-*"))
        or any(extensions.glob("github.copilot-chat-*"))
    )


def _copilot_surfaces(
    root: Path,
    home: Path,
    *,
    cli_executable: str | None,
) -> tuple[bool, bool]:
    """Return whether Copilot CLI and VS Code surfaces are present/configured."""
    cli = bool(cli_executable or copilot_cli_configured(home))
    vscode = bool(
        _copilot_vscode_installed(home)
        or copilot_mcp_path(root).exists()
        or copilot_vscode_configured(root)
    )
    return cli, vscode


def detect_hosts(
    root: Path,
    *,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> list[HostStatus]:
    """Detect supported hosts and whether ACCO is already configured."""
    root = root.resolve()
    home = home or Path.home()
    executable = {
        name: which(HOST_EXECUTABLES[name])
        for name in HOSTS
    }
    claude_paths = (claude_settings_path(root), claude_mcp_path(root))
    cursor_path = cursor_mcp_path(root)
    cursor_native_path = cursor_hooks_path(root)
    gemini_path = gemini_settings_path(root)
    qwen_path = qwen_settings_path(root)
    codex_path = codex_config_path(home)
    codex_text = codex_path.read_text(encoding="utf-8") if codex_path.exists() else ""
    opencode_path = opencode_mcp_path(root)
    openclaw_path = openclaw_config_path(home)
    hermes_path = hermes_config_path(home)
    copilot_path = copilot_mcp_path(root)
    copilot_cli_path = copilot_cli_config_path(home)
    copilot_cli_surface, copilot_vscode_surface = _copilot_surfaces(
        root,
        home,
        cli_executable=executable["copilot"],
    )
    copilot_executable = executable["copilot"] or (
        which("code") if copilot_vscode_surface else None
    )
    antigravity_path = antigravity_mcp_path(root)
    antigravity_global = antigravity_global_mcp_path(home)
    return [
        HostStatus(
            "claude",
            bool(executable["claude"] or (home / ".claude").exists()),
            _claude_hooks_configured(root) and _json_mcp_configured(claude_paths[1]),
            executable["claude"],
            tuple(str(path) for path in claude_paths),
            ("hooks", "mcp"),
        ),
        HostStatus(
            "cursor",
            bool(
                executable["cursor"]
                or (home / ".cursor").exists()
                or (root / ".cursor").exists()
            ),
            _json_mcp_configured(cursor_path)
            and native_hooks_configured(root, "cursor"),
            executable["cursor"],
            (str(cursor_path), str(cursor_native_path)),
            ("mcp", "native-hooks"),
        ),
        HostStatus(
            "codex",
            bool(executable["codex"] or (home / ".codex").exists()),
            CODEX_START in codex_text and CODEX_END in codex_text,
            executable["codex"],
            (str(codex_path),),
            ("mcp",),
        ),
        HostStatus(
            "opencode",
            bool(
                executable["opencode"]
                or (root / ".opencode").exists()
                or (home / ".config" / "opencode").exists()
            ),
            opencode_configured(root),
            executable["opencode"],
            (str(opencode_path),),
            ("mcp", "project-local"),
        ),
        HostStatus(
            "openclaw",
            bool(executable["openclaw"] or (home / ".openclaw").exists()),
            openclaw_configured(home),
            executable["openclaw"],
            (str(openclaw_path),),
            ("mcp", "native-config-cli"),
        ),
        HostStatus(
            "hermes",
            bool(executable["hermes"] or (home / ".hermes").exists()),
            hermes_configured(home),
            executable["hermes"],
            (str(hermes_path),),
            ("mcp", "managed-yaml-block"),
        ),
        HostStatus(
            "copilot",
            bool(copilot_cli_surface or copilot_vscode_surface),
            copilot_configured(
                root,
                home=home,
                cli_required=copilot_cli_surface,
                vscode_required=copilot_vscode_surface,
            )
            and (
                not copilot_cli_surface
                or native_hooks_configured(root, "copilot")
            ),
            copilot_executable,
            (
                str(copilot_cli_path),
                str(copilot_path),
                str(copilot_hooks_path(root)),
            ),
            tuple(
                ["mcp"]
                + (["copilot-cli", "native-hooks"] if copilot_cli_surface else [])
                + (["vscode-workspace"] if copilot_vscode_surface else [])
            ),
        ),
        HostStatus(
            "antigravity",
            bool(
                executable["antigravity"]
                or (root / ".agents").exists()
                or antigravity_global.exists()
            ),
            antigravity_configured(root),
            executable["antigravity"],
            (str(antigravity_path), str(antigravity_global)),
            ("mcp", "workspace-local"),
        ),
        HostStatus(
            "gemini",
            bool(
                executable["gemini"]
                or (root / ".gemini").exists()
                or (home / ".gemini").exists()
            ),
            native_hooks_configured(root, "gemini"),
            executable["gemini"],
            (str(gemini_path),),
            ("native-hooks", "project-local"),
        ),
        HostStatus(
            "qwen",
            bool(
                executable["qwen"]
                or (root / ".qwen").exists()
                or (home / ".qwen").exists()
            ),
            native_hooks_configured(root, "qwen"),
            executable["qwen"],
            (str(qwen_path),),
            ("native-hooks", "project-local"),
        ),
    ]


def write_default_config(root: Path) -> Path:
    """Create project configuration if it does not already exist."""
    path = root.resolve() / CONFIG_NAME
    if not path.exists():
        _atomic_write(path, DEFAULT_CONFIG)
    return path


def setup_integrations(
    root: Path,
    hosts: tuple[str, ...] | None = None,
    *,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    runner: RunCommand = run_command,
    install_lean: bool = True,
) -> dict:
    """Configure detected or explicitly requested hosts idempotently."""
    root = root.resolve()
    home = home or Path.home()
    detected = detect_hosts(root, home=home, which=which)
    if hosts:
        requested = (
            tuple(item.name for item in detected if item.detected)
            if "all" in hosts
            else tuple(dict.fromkeys(hosts))
        )
    else:
        requested = tuple(item.name for item in detected if item.detected)
    unknown = sorted(set(requested) - set(HOSTS))
    if unknown:
        raise ValueError(f"Unsupported host(s): {', '.join(unknown)}")
    if not root.is_dir():
        raise ValueError(f"Project path is not a directory: {root}")

    # Preflight every managed surface before the first mutation so a conflict in
    # one host cannot leave earlier hosts partially configured.
    if "claude" in requested:
        _validate_json_object(claude_settings_path(root))
        _validate_json_object(claude_mcp_path(root))
    if "cursor" in requested:
        _validate_json_object(cursor_mcp_path(root))
        _validate_json_object(cursor_hooks_path(root))
    if "codex" in requested:
        _validate_codex_manageable(codex_config_path(home))
    if "opencode" in requested:
        validate_opencode_manageable(root)
        _validate_json_object(opencode_mcp_path(root))
    if "copilot" in requested:
        copilot_cli_surface, copilot_vscode_surface = _copilot_surfaces(
            root,
            home,
            cli_executable=which(HOST_EXECUTABLES["copilot"]),
        )
        if not copilot_cli_surface and not copilot_vscode_surface:
            raise ValueError(
                "Copilot setup requires either the copilot CLI or the "
                "GitHub Copilot VS Code extension."
            )
        if copilot_cli_surface:
            validate_copilot_cli_manageable(home)
            validate_copilot_hooks_manageable(root)
        if copilot_vscode_surface:
            _validate_json_object(copilot_mcp_path(root))
    if "antigravity" in requested:
        _validate_json_object(antigravity_mcp_path(root))
    if "gemini" in requested:
        _validate_json_object(gemini_settings_path(root))
    if "qwen" in requested:
        _validate_json_object(qwen_settings_path(root))
    if "hermes" in requested:
        validate_hermes_manageable(hermes_config_path(home))
    if "openclaw" in requested and not which(HOST_EXECUTABLES["openclaw"]):
        raise ValueError(
            "OpenClaw setup requires the openclaw executable so ACCO can "
            "use its validated native MCP registry."
        )

    changed: list[str] = []
    lean_skill = None
    config_path = write_default_config(root)
    if "claude" in requested:
        install_claude_hooks(root, templates=True)
        update_json(claude_mcp_path(root), _merge_mcp(root))
        if install_lean:
            lean_skill = _ensure_managed_lean_skill(root)
        changed.append("claude")
    if "cursor" in requested:
        update_json(cursor_mcp_path(root), _merge_mcp(root))
        install_cursor_hooks(root)
        changed.append("cursor")
    if "codex" in requested:
        _install_codex(codex_config_path(home))
        changed.append("codex")
    if "opencode" in requested:
        install_opencode(root)
        changed.append("opencode")
    if "openclaw" in requested:
        install_openclaw(root, runner=runner)
        changed.append("openclaw")
    if "hermes" in requested:
        install_hermes(root, home)
        changed.append("hermes")
    if "copilot" in requested:
        cli_executable = which(HOST_EXECUTABLES["copilot"])
        copilot_cli_surface, copilot_vscode_surface = _copilot_surfaces(
            root,
            home,
            cli_executable=cli_executable,
        )
        if cli_executable:
            install_copilot_cli(home=home, runner=runner)
        if copilot_cli_surface:
            install_copilot_hooks(root)
        if copilot_vscode_surface:
            install_copilot_vscode(root)
        changed.append("copilot")
    if "antigravity" in requested:
        install_antigravity(root)
        changed.append("antigravity")
    if "gemini" in requested:
        install_gemini_hooks(root)
        changed.append("gemini")
    if "qwen" in requested:
        install_qwen_hooks(root)
        changed.append("qwen")

    return {
        "root": str(root),
        "config": str(config_path),
        "requested_hosts": list(requested),
        "configured_hosts": changed,
        "lean_skill": lean_skill,
        "profile": "safe",
        "detected": [asdict(item) for item in detect_hosts(root, home=home, which=which)],
    }


def uninstall_integrations(
    root: Path,
    hosts: tuple[str, ...] | None = None,
    *,
    home: Path | None = None,
    remove_config: bool = False,
    which: Callable[[str], str | None] = shutil.which,
    runner: RunCommand = run_command,
) -> dict:
    """Remove only ACCO-owned integration entries."""
    root = root.resolve()
    home = home or Path.home()
    requested = HOSTS if not hosts or "all" in hosts else tuple(dict.fromkeys(hosts))
    unknown = sorted(set(requested) - set(HOSTS))
    if unknown:
        raise ValueError(f"Unsupported host(s): {', '.join(unknown)}")
    if not root.is_dir():
        raise ValueError(f"Project path is not a directory: {root}")
    if "claude" in requested:
        _validate_json_object(claude_settings_path(root))
        _validate_json_object(claude_mcp_path(root))
    if "cursor" in requested:
        _validate_json_object(cursor_mcp_path(root))\n        _validate_json_object(cursor_hooks_path(root))
    if "opencode" in requested:
        _validate_json_object(opencode_mcp_path(root))
    if "copilot" in requested:
        if copilot_vscode_configured(root):
            _validate_json_object(copilot_mcp_path(root))
        if copilot_hooks_path(root).exists():
            validate_copilot_hooks_manageable(root)
        if copilot_cli_configured(home):
            validate_copilot_cli_manageable(home)
            if not which(HOST_EXECUTABLES["copilot"]):
                raise ValueError(
                    "Copilot CLI uninstall requires the copilot executable "
                    "because its user MCP registry is mutated natively."
                )
    if "antigravity" in requested:
        _validate_json_object(antigravity_mcp_path(root))
    if "gemini" in requested:
        _validate_json_object(gemini_settings_path(root))
    if "qwen" in requested:
        _validate_json_object(qwen_settings_path(root))
    if "hermes" in requested:
        validate_hermes_manageable(hermes_config_path(home))
    if (
        "openclaw" in requested
        and openclaw_configured(home)
        and not which(HOST_EXECUTABLES["openclaw"])
    ):
        raise ValueError(
            "OpenClaw uninstall requires the openclaw executable because its "
            "JSON5 registry is mutated through the host-native command."
        )

    removed: list[str] = []
    if "claude" in requested:
        uninstall_claude_hooks(root)
        _remove_managed_claude_skill(root)
        _remove_managed_lean_skill(root)
        path = claude_mcp_path(root)
        if path.exists():
            update_json(path, _remove_mcp)
        removed.append("claude")
    if "cursor" in requested:
        path = cursor_mcp_path(root)
        if path.exists():
            update_json(path, _remove_mcp)
        uninstall_cursor_hooks(root)
        removed.append("cursor")
    if "codex" in requested:
        _uninstall_codex(codex_config_path(home))
        removed.append("codex")
    if "opencode" in requested:
        uninstall_opencode(root)
        removed.append("opencode")
    if "openclaw" in requested:
        uninstall_openclaw(home, runner=runner)
        removed.append("openclaw")
    if "hermes" in requested:
        uninstall_hermes(home)
        removed.append("hermes")
    if "copilot" in requested:
        if copilot_hooks_path(root).exists():
            uninstall_copilot_hooks(root)
        if copilot_cli_configured(home):
            uninstall_copilot_cli(home=home, runner=runner)
        uninstall_copilot_vscode(root)
        removed.append("copilot")
    if "antigravity" in requested:
        uninstall_antigravity(root)
        removed.append("antigravity")
    if "gemini" in requested:
        uninstall_gemini_hooks(root)
        removed.append("gemini")
    if "qwen" in requested:
        uninstall_qwen_hooks(root)
        removed.append("qwen")
    config = root / CONFIG_NAME
    if remove_config and config.exists():
        config.unlink()
    return {"root": str(root), "removed_hosts": removed, "config_removed": remove_config}


def _version() -> str:
    """Return installed package version with a source-checkout fallback."""
    try:
        return metadata.version("ai-coding-context-optimizer")
    except metadata.PackageNotFoundError:
        from . import __version__

        return __version__


def doctor_report(
    root: Path,
    *,
    home: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    index: bool = True,
) -> dict:
    """Build a consolidated health report for installation and integrations."""
    root = root.resolve()
    home = home or Path.home()
    if not root.is_dir():
        raise ValueError(f"Project path is not a directory: {root}")
    config_path = find_project_config(root)
    config_error = None
    try:
        runtime = asdict(settings_for(root))
    except ValueError as exc:
        runtime = None
        config_error = str(exc)
    index_status = None
    index_error = None
    if index:
        try:
            index_status = RepositoryContextService(root).status()
        except (OSError, ValueError) as exc:
            index_error = str(exc)
    hosts = detect_hosts(root, home=home, which=which)
    transcripts = len(transcript_paths(root))
    executable = which("acco")
    ready_hosts = [item.name for item in hosts if item.configured]
    detected_hosts = [item.name for item in hosts if item.detected]
    ready = bool(ready_hosts and not config_error and not index_error)
    return {
        "ready": ready,
        "version": _version(),
        "acco_executable": executable,
        "root": str(root),
        "config_path": str(config_path) if config_path else None,
        "config_error": config_error,
        "runtime": runtime,
        "detected_hosts": detected_hosts,
        "configured_hosts": ready_hosts,
        "hosts": [asdict(item) for item in hosts],
        "index": index_status,
        "index_error": index_error,
        "claude_transcripts": transcripts,
    }
