"""Persistent provider-proxy profiles and durable host attachment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import urlopen
from xml.sax.saxutils import escape

from .config import update_json
from .install import settings_path as claude_settings_path
from .provider_proxy import ProviderProxyConfig, run_provider_proxy
from .state import state_dir
from .wrapper import PROVIDERS

PROFILE_SCHEMA = 1
DURABLE_HOST_PROVIDER = {
    "claude": "anthropic",
    "codex": "openai",
}
CLAUDE_PROFILE_ENV = "ACCO_PERSISTENT_PROXY_PROFILE"
CODEX_START_PREFIX = "# >>> acco persistent proxy "
CODEX_END_PREFIX = "# <<< acco persistent proxy "


@dataclass(frozen=True)
class PersistentProxyProfile:
    """Serializable persistent proxy configuration without provider credentials."""

    profile_id: str
    root: str
    provider: str
    upstream: str
    port: int
    hosts: tuple[str, ...]
    service_kind: str
    service_artifact: str

    @property
    def local_base_url(self) -> str:
        """Return the provider-compatible stable loopback URL."""
        base = f"http://127.0.0.1:{self.port}"
        return base + "/v1" if self.provider == "openai" else base

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe profile record."""
        return {"schema": PROFILE_SCHEMA, **asdict(self), "local_base_url": self.local_base_url}


RunCommand = Callable[..., subprocess.CompletedProcess]


def _profiles_root() -> Path:
    """Return the private directory that owns persistent proxy state."""
    return state_dir() / "persistent-proxy"


def _profile_path(profile_id: str) -> Path:
    """Return one profile manifest path."""
    return _profiles_root() / f"{profile_id}.json"


def _profile_id(root: Path, provider: str) -> str:
    """Return a stable project/provider identity safe for service names."""
    identity = f"{root.resolve()}\0{provider.strip().lower()}"
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


def _runtime_instance_id(profile: PersistentProxyProfile) -> str:
    """Return a content-free identity that changes with runtime configuration."""
    identity = json.dumps(
        {
            "profile_id": profile.profile_id,
            "root": profile.root,
            "provider": profile.provider,
            "upstream": profile.upstream,
            "port": profile.port,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def _atomic_text(path: Path, text: str) -> None:
    """Atomically write a private UTF-8 text artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
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


def _validate_upstream(provider: str, upstream: str) -> str:
    """Validate a persistent upstream and reject secrets in service artifacts."""
    if provider not in PROVIDERS:
        raise ValueError(
            "persistent proxy provider must be one of: "
            + ", ".join(sorted(PROVIDERS))
        )
    value = upstream.rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("persistent proxy upstream must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("persistent proxy upstream must not contain credentials")
    if parsed.scheme == "http" and (parsed.hostname or "") not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise ValueError("plain HTTP persistent upstream is allowed only for localhost")
    return value


def _free_port() -> int:
    """Choose one currently free loopback port for a new persistent profile."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _save_profile(profile: PersistentProxyProfile) -> Path:
    """Persist one profile without any auth material."""
    path = _profile_path(profile.profile_id)
    _atomic_text(path, json.dumps(profile.to_dict(), indent=2) + "\n")
    return path


def load_profile(profile_id: str) -> PersistentProxyProfile:
    """Load and validate one persistent profile."""
    path = _profile_path(profile_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"persistent proxy profile not found: {profile_id}") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid persistent proxy profile: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"unsupported persistent proxy profile: {path}")
    provider = str(payload.get("provider", "")).strip().lower()
    upstream = _validate_upstream(provider, str(payload.get("upstream", "")))
    port = int(payload.get("port", 0))
    if not 1 <= port <= 65535:
        raise ValueError(f"invalid persistent proxy port in {path}")
    return PersistentProxyProfile(
        profile_id=str(payload.get("profile_id", "")),
        root=str(payload.get("root", "")),
        provider=provider,
        upstream=upstream,
        port=port,
        hosts=tuple(str(item) for item in payload.get("hosts", [])),
        service_kind=str(payload.get("service_kind", "")),
        service_artifact=str(payload.get("service_artifact", "")),
    )


def profiles_for_root(root: Path) -> tuple[PersistentProxyProfile, ...]:
    """Return all readable persistent profiles for one project."""
    resolved = str(root.resolve())
    profiles: list[PersistentProxyProfile] = []
    directory = _profiles_root()
    if not directory.exists():
        return ()
    for path in sorted(directory.glob("*.json")):
        try:
            profile = load_profile(path.stem)
        except ValueError:
            continue
        if profile.root == resolved:
            profiles.append(profile)
    return tuple(profiles)


def _resolve_acco_command() -> list[str]:
    """Return an absolute command suitable for an OS service definition."""
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    executable = shutil.which("acco")
    if executable:
        return [str(Path(executable).resolve())]
    return [str(Path(sys.executable).resolve()), "-m", "acco.entry"]


def _service_command(profile_id: str) -> list[str]:
    """Return the credential-free foreground runner command."""
    return [
        *_resolve_acco_command(),
        "proxy-run",
        profile_id,
        "--state-dir",
        str(state_dir().resolve()),
    ]


def _service_kind(platform: str | None = None) -> str:
    """Return the native current-user supervisor kind."""
    value = platform or sys.platform
    if value.startswith("linux"):
        return "systemd-user"
    if value == "darwin":
        return "launchd-user"
    if value.startswith("win"):
        return "windows-task"
    raise ValueError(f"persistent proxy is not supported on platform: {value}")


def _systemd_escape_arg(value: str) -> str:
    """Quote one systemd ExecStart argument conservatively."""
    return shlex.quote(value).replace("%", "%%")


def _service_artifact(profile_id: str, kind: str, *, home: Path | None = None) -> Path:
    """Return the native supervisor artifact path."""
    home = home or Path.home()
    if kind == "systemd-user":
        return home / ".config" / "systemd" / "user" / f"acco-proxy-{profile_id}.service"
    if kind == "launchd-user":
        return home / "Library" / "LaunchAgents" / f"com.acco.proxy.{profile_id}.plist"
    if kind == "windows-task":
        return _profile_path(profile_id)
    raise ValueError(f"unsupported service kind: {kind}")


def render_service_artifact(
    profile_id: str,
    *,
    kind: str,
    home: Path | None = None,
) -> tuple[Path, str | None]:
    """Render the native autostart artifact without installing it."""
    path = _service_artifact(profile_id, kind, home=home)
    command = _service_command(profile_id)
    if kind == "systemd-user":
        exec_start = " ".join(_systemd_escape_arg(item) for item in command)
        text = (
            "[Unit]\n"
            f"Description=ACCO persistent provider proxy {profile_id}\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={exec_start}\n"
            "Restart=on-failure\n"
            "RestartSec=2\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        return path, text
    if kind == "launchd-user":
        args = "".join(f"<string>{escape(item)}</string>" for item in command)
        label = f"com.acco.proxy.{profile_id}"
        text = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>'
            f"<key>Label</key><string>{label}</string>"
            f"<key>ProgramArguments</key><array>{args}</array>"
            "<key>RunAtLoad</key><true/>"
            "<key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>"
            "</dict></plist>\n"
        )
        return path, text
    if kind == "windows-task":
        return path, None
    raise ValueError(f"unsupported service kind: {kind}")


def _run(
    runner: RunCommand,
    argv: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Invoke one supervisor command with stable text/capture behavior."""
    return runner(
        argv,
        check=check,
        text=True,
        capture_output=True,
    )


def install_service(
    profile_id: str,
    *,
    kind: str | None = None,
    home: Path | None = None,
    runner: RunCommand = subprocess.run,
) -> tuple[str, str]:
    """Install and start one current-user autostart service."""
    selected = kind or _service_kind()
    path, text = render_service_artifact(profile_id, kind=selected, home=home)
    if text is not None:
        _atomic_text(path, text)

    if selected == "systemd-user":
        _run(runner, ["systemctl", "--user", "daemon-reload"])
        _run(
            runner,
            [
                "systemctl",
                "--user",
                "enable",
                path.name,
            ],
        )
        _run(
            runner,
            ["systemctl", "--user", "restart", path.name],
        )
    elif selected == "launchd-user":
        uid = str(os.getuid())
        label = f"com.acco.proxy.{profile_id}"
        _run(
            runner,
            ["launchctl", "bootout", f"gui/{uid}", str(path)],
            check=False,
        )
        _run(runner, ["launchctl", "bootstrap", f"gui/{uid}", str(path)])
        _run(runner, ["launchctl", "enable", f"gui/{uid}/{label}"])
    elif selected == "windows-task":
        task = f"ACCO Proxy {profile_id}"
        command = subprocess.list2cmdline(_service_command(profile_id))
        _run(runner, ["schtasks", "/End", "/TN", task], check=False)
        _run(
            runner,
            [
                "schtasks",
                "/Create",
                "/TN",
                task,
                "/TR",
                command,
                "/SC",
                "ONLOGON",
                "/RL",
                "LIMITED",
                "/F",
            ],
        )
        _run(runner, ["schtasks", "/Run", "/TN", task])
    else:
        raise ValueError(f"unsupported service kind: {selected}")
    return selected, str(path)


def stop_service(
    profile: PersistentProxyProfile,
    *,
    runner: RunCommand = subprocess.run,
) -> None:
    """Stop one installed user service without deleting its autostart registration."""
    if profile.service_kind == "systemd-user":
        _run(
            runner,
            ["systemctl", "--user", "stop", Path(profile.service_artifact).name],
            check=False,
        )
    elif profile.service_kind == "launchd-user":
        label = f"com.acco.proxy.{profile.profile_id}"
        _run(
            runner,
            ["launchctl", "kill", "SIGTERM", f"gui/{os.getuid()}/{label}"],
            check=False,
        )
    elif profile.service_kind == "windows-task":
        _run(
            runner,
            ["schtasks", "/End", "/TN", f"ACCO Proxy {profile.profile_id}"],
            check=False,
        )


def start_service(
    profile: PersistentProxyProfile,
    *,
    runner: RunCommand = subprocess.run,
) -> None:
    """Start one installed persistent proxy service."""
    if profile.service_kind == "systemd-user":
        _run(
            runner,
            ["systemctl", "--user", "start", Path(profile.service_artifact).name],
        )
    elif profile.service_kind == "launchd-user":
        label = f"com.acco.proxy.{profile.profile_id}"
        _run(
            runner,
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"],
        )
    elif profile.service_kind == "windows-task":
        _run(
            runner,
            ["schtasks", "/Run", "/TN", f"ACCO Proxy {profile.profile_id}"],
        )


def uninstall_service(
    profile: PersistentProxyProfile,
    *,
    runner: RunCommand = subprocess.run,
) -> None:
    """Remove one current-user autostart registration owned by ACCO."""
    stop_service(profile, runner=runner)
    artifact = Path(profile.service_artifact)
    if profile.service_kind == "systemd-user":
        _run(
            runner,
            [
                "systemctl",
                "--user",
                "disable",
                artifact.name,
            ],
            check=False,
        )
        artifact.unlink(missing_ok=True)
        _run(runner, ["systemctl", "--user", "daemon-reload"], check=False)
    elif profile.service_kind == "launchd-user":
        _run(
            runner,
            [
                "launchctl",
                "bootout",
                f"gui/{os.getuid()}",
                str(artifact),
            ],
            check=False,
        )
        artifact.unlink(missing_ok=True)
    elif profile.service_kind == "windows-task":
        _run(
            runner,
            [
                "schtasks",
                "/Delete",
                "/TN",
                f"ACCO Proxy {profile.profile_id}",
                "/F",
            ],
            check=False,
        )


def proxy_alive(profile: PersistentProxyProfile, timeout: float = 0.4) -> bool:
    """Return whether the expected ACCO instance owns the stable listener."""
    url = f"http://127.0.0.1:{profile.port}/__acco/health"
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read())
    except (OSError, ValueError):
        return False
    expected_root = hashlib.sha256(profile.root.encode()).hexdigest()[:16]
    return (
        isinstance(payload, dict)
        and payload.get("ok") is True
        and payload.get("provider") == profile.provider
        and payload.get("instance_id") == _runtime_instance_id(profile)
        and payload.get("root_fingerprint") == expected_root
    )


def _wait_profile_ready(
    profile: PersistentProxyProfile,
    *,
    timeout_seconds: float = 6.0,
) -> bool:
    """Wait briefly for a just-installed native service to own its listener."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if proxy_alive(profile):
            return True
        time.sleep(0.1)
    return False


def _read_json_object(path: Path) -> dict[str, Any]:
    """Read one JSON object or fail closed before mutating user configuration."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"refusing invalid JSON host configuration: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def attach_claude(profile: PersistentProxyProfile) -> None:
    """Persist Claude's documented project environment routing to one ACCO profile."""
    if profile.provider != "anthropic":
        raise ValueError("Claude persistent attachment requires an Anthropic profile")
    path = claude_settings_path(Path(profile.root))
    existing = _read_json_object(path)
    env = existing.get("env")
    env_map = dict(env) if isinstance(env, dict) else {}
    current = str(env_map.get("ANTHROPIC_BASE_URL", "")).strip()
    owner = str(env_map.get(CLAUDE_PROFILE_ENV, "")).strip()
    if current and owner != profile.profile_id:
        raise ValueError(
            "refusing to replace user-managed Claude ANTHROPIC_BASE_URL; "
            "remove that override before enabling persistent ACCO routing"
        )

    def mutate(payload: dict) -> dict:
        updated = dict(payload)
        child = updated.get("env")
        child = dict(child) if isinstance(child, dict) else {}
        child["ANTHROPIC_BASE_URL"] = profile.local_base_url
        child[CLAUDE_PROFILE_ENV] = profile.profile_id
        updated["env"] = child
        return updated

    update_json(path, mutate)


def _validate_claude_detach(profile: PersistentProxyProfile) -> None:
    """Refuse service removal when Claude still points at us without ownership."""
    path = claude_settings_path(Path(profile.root))
    if not path.exists():
        return
    payload = _read_json_object(path)
    env = payload.get("env")
    if not isinstance(env, dict):
        return
    owner = str(env.get(CLAUDE_PROFILE_ENV, "")).strip()
    current = str(env.get("ANTHROPIC_BASE_URL", "")).strip()
    if not owner and current == profile.local_base_url:
        raise ValueError(
            "Claude still points at this ACCO proxy but its ownership marker is "
            "missing; restore/remove the routing explicitly before uninstall"
        )


def detach_claude(profile: PersistentProxyProfile) -> None:
    """Remove only Claude routing still owned by this persistent profile."""
    _validate_claude_detach(profile)
    path = claude_settings_path(Path(profile.root))
    if not path.exists():
        return

    def mutate(payload: dict) -> dict:
        updated = dict(payload)
        env = updated.get("env")
        if not isinstance(env, dict):
            return updated
        child = dict(env)
        if child.get(CLAUDE_PROFILE_ENV) != profile.profile_id:
            return updated
        if child.get("ANTHROPIC_BASE_URL") == profile.local_base_url:
            child.pop("ANTHROPIC_BASE_URL", None)
        child.pop(CLAUDE_PROFILE_ENV, None)
        if child:
            updated["env"] = child
        else:
            updated.pop("env", None)
        return updated

    update_json(path, mutate)


def _codex_markers(profile_id: str) -> tuple[str, str]:
    """Return unique ownership markers for one Codex persistent profile."""
    return (
        f"{CODEX_START_PREFIX}{profile_id} >>>",
        f"{CODEX_END_PREFIX}{profile_id} <<<",
    )


def _strip_marked_block(text: str, profile_id: str) -> str:
    """Remove one complete ACCO persistent Codex block."""
    start_marker, end_marker = _codex_markers(profile_id)
    start = text.find(start_marker)
    if start < 0:
        return text
    end = text.find(end_marker, start)
    if end < 0:
        raise ValueError("ACCO persistent Codex block is incomplete")
    end += len(end_marker)
    while end < len(text) and text[end] in "\r\n":
        end += 1
    return (text[:start].rstrip() + "\n\n" + text[end:].lstrip()).strip() + "\n"


def _codex_chatgpt_auth(path: Path) -> bool:
    """Detect the non-secret Codex auth mode needed by a custom provider."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    mode = payload.get("auth_mode")
    if isinstance(mode, str):
        return mode.lower() == "chatgpt"
    tokens = payload.get("tokens")
    return (
        isinstance(tokens, dict)
        and isinstance(tokens.get("account_id"), str)
        and bool(tokens["account_id"].strip())
    )


def _root_toml_conflicts(text: str) -> tuple[str, ...]:
    """Return provider-routing root keys outside TOML tables."""
    first_table = re.search(r"(?m)^[ \t]*\[", text)
    root = text[: first_table.start()] if first_table else text
    found: list[str] = []
    for key in ("model_provider", "openai_base_url"):
        if re.search(rf"(?m)^[ \t]*{key}[ \t]*=", root):
            found.append(key)
    return tuple(found)


def attach_codex(profile: PersistentProxyProfile, *, home: Path | None = None) -> None:
    """Persist Codex routing through an owned custom model-provider block."""
    if profile.provider != "openai":
        raise ValueError("Codex persistent attachment requires an OpenAI profile")
    home = home or Path.home()
    path = Path(profile.root) / ".codex" / "config.toml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    start_marker, end_marker = _codex_markers(profile.profile_id)
    if (start_marker in text) != (end_marker in text):
        raise ValueError("ACCO persistent Codex block is incomplete")
    cleaned = _strip_marked_block(text, profile.profile_id) if start_marker in text else text
    if "[model_providers.acco]" in cleaned:
        raise ValueError(
            "refusing to replace unmanaged [model_providers.acco] in Codex config"
        )
    conflicts = _root_toml_conflicts(cleaned)
    if conflicts:
        raise ValueError(
            "refusing to replace user-managed Codex root routing: "
            + ", ".join(conflicts)
        )

    first_table = re.search(r"(?m)^[ \t]*\[", cleaned)
    split = first_table.start() if first_table else len(cleaned)
    root_text = cleaned[:split].rstrip()
    tables = cleaned[split:].lstrip()
    requires_auth = _codex_chatgpt_auth(home / ".codex" / "auth.json")
    auth_line = "requires_openai_auth = true\n" if requires_auth else ""
    block = (
        f"{start_marker}\n"
        'model_provider = "acco"\n'
        f'openai_base_url = "{profile.local_base_url}"\n\n'
        "[model_providers.acco]\n"
        'name = "ACCO persistent proxy"\n'
        f'base_url = "{profile.local_base_url}"\n'
        "supports_websockets = false\n"
        f"{auth_line}"
        f"{end_marker}\n"
    )
    rendered = (root_text + "\n\n" if root_text else "") + block
    if tables:
        rendered += "\n" + tables.rstrip() + "\n"
    _atomic_text(path, rendered)


def _validate_codex_detach(profile: PersistentProxyProfile) -> None:
    """Refuse removal when Codex appears routed to us without complete markers."""
    path = Path(profile.root) / ".codex" / "config.toml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    start_marker, end_marker = _codex_markers(profile.profile_id)
    has_start = start_marker in text
    has_end = end_marker in text
    if has_start != has_end:
        raise ValueError("ACCO persistent Codex block is incomplete")
    if has_start:
        return
    if (
        profile.local_base_url in text
        and (
            '[model_providers.acco]' in text
            or re.search(r'(?m)^[ \t]*model_provider[ \t]*=[ \t]*"acco"', text)
        )
    ):
        raise ValueError(
            "Codex still points at this ACCO proxy but its ownership markers are "
            "missing; restore/remove the routing explicitly before uninstall"
        )


def detach_codex(profile: PersistentProxyProfile, *, home: Path | None = None) -> None:
    """Remove only the marked persistent Codex provider block."""
    del home
    _validate_codex_detach(profile)
    path = Path(profile.root) / ".codex" / "config.toml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    cleaned = _strip_marked_block(text, profile.profile_id)
    if cleaned != text:
        _atomic_text(path, cleaned)


def attach_host(
    host: str,
    profile: PersistentProxyProfile,
    *,
    home: Path | None = None,
) -> None:
    """Attach one supported host to its provider-matched persistent profile."""
    if host == "claude":
        attach_claude(profile)
        return
    if host == "codex":
        attach_codex(profile, home=home)
        return
    raise ValueError(
        f"persistent automatic provider attachment is not supported for {host!r}; "
        "use acco wrap for that host"
    )


def validate_detach_host(
    host: str,
    profile: PersistentProxyProfile,
) -> None:
    """Preflight host ownership before any persistent service is removed."""
    if host == "claude":
        _validate_claude_detach(profile)
    elif host == "codex":
        _validate_codex_detach(profile)


def detach_host(
    host: str,
    profile: PersistentProxyProfile,
    *,
    home: Path | None = None,
) -> None:
    """Detach one host only when the routing is still ACCO-owned."""
    if host == "claude":
        detach_claude(profile)
    elif host == "codex":
        detach_codex(profile, home=home)


def install_persistent_profiles(
    root: Path,
    hosts: tuple[str, ...],
    *,
    upstreams: dict[str, str] | None = None,
    ports: dict[str, int] | None = None,
    kind: str | None = None,
    home: Path | None = None,
    runner: RunCommand = subprocess.run,
) -> dict[str, Any]:
    """Install provider profiles, native autostart, and durable host routing."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"project path is not a directory: {root}")
    requested = tuple(dict.fromkeys(hosts))
    unknown = sorted(set(requested) - set(DURABLE_HOST_PROVIDER))
    if unknown:
        raise ValueError(
            "persistent auto-attachment currently supports only: "
            + ", ".join(sorted(DURABLE_HOST_PROVIDER))
            + "; unsupported: "
            + ", ".join(unknown)
        )
    provider_hosts: dict[str, list[str]] = {}
    for host in requested:
        provider_hosts.setdefault(DURABLE_HOST_PROVIDER[host], []).append(host)

    installed: list[tuple[PersistentProxyProfile, PersistentProxyProfile | None]] = []
    attached: list[tuple[str, str]] = []
    try:
        for provider, provider_host_names in sorted(provider_hosts.items()):
            profile_id = _profile_id(root, provider)
            try:
                previous = load_profile(profile_id)
            except ValueError:
                previous = None
            upstream = _validate_upstream(
                provider,
                (upstreams or {}).get(provider, PROVIDERS[provider].upstream),
            )
            port = int(
                (ports or {}).get(
                    provider,
                    previous.port if previous is not None else _free_port(),
                )
            )
            if not 1 <= port <= 65535:
                raise ValueError("persistent proxy port must be in 1..65535")

            selected_kind = kind or _service_kind()
            artifact = str(_service_artifact(profile_id, selected_kind, home=home))
            profile = PersistentProxyProfile(
                profile_id=profile_id,
                root=str(root),
                provider=provider,
                upstream=upstream,
                port=port,
                hosts=tuple(provider_host_names),
                service_kind=selected_kind,
                service_artifact=artifact,
            )
            _save_profile(profile)
            installed.append((profile, previous))
            service_kind, service_artifact = install_service(
                profile_id,
                kind=selected_kind,
                home=home,
                runner=runner,
            )
            if service_kind != profile.service_kind or service_artifact != profile.service_artifact:
                raise RuntimeError("persistent proxy supervisor artifact mismatch")
            if not _wait_profile_ready(profile):
                raise RuntimeError(
                    f"persistent {provider} proxy did not become ready on "
                    f"127.0.0.1:{profile.port}"
                )
            for host in provider_host_names:
                attach_host(host, profile, home=home)
                attached.append((profile.profile_id, host))
    except BaseException:
        for profile, previous in reversed(installed):
            if previous is None:
                for host in profile.hosts:
                    if (profile.profile_id, host) in attached:
                        try:
                            detach_host(host, profile, home=home)
                        except (OSError, ValueError):
                            pass
                try:
                    uninstall_service(profile, runner=runner)
                except (OSError, subprocess.SubprocessError):
                    pass
                _profile_path(profile.profile_id).unlink(missing_ok=True)
                continue

            _save_profile(previous)
            try:
                install_service(
                    previous.profile_id,
                    kind=previous.service_kind,
                    home=home,
                    runner=runner,
                )
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
            for host in previous.hosts:
                try:
                    attach_host(host, previous, home=home)
                except (OSError, ValueError):
                    pass
        raise

    return {
        "root": str(root),
        "hosts": list(requested),
        "profiles": [profile.to_dict() for profile, _previous in installed],
    }


def uninstall_persistent_profiles(
    root: Path,
    *,
    home: Path | None = None,
    runner: RunCommand = subprocess.run,
) -> dict[str, Any]:
    """Detach hosts and remove all persistent profiles for one project."""
    profiles = profiles_for_root(root)
    for profile in profiles:
        for host in profile.hosts:
            validate_detach_host(host, profile)

    removed: list[str] = []
    for profile in profiles:
        for host in profile.hosts:
            detach_host(host, profile, home=home)
        uninstall_service(profile, runner=runner)
        _profile_path(profile.profile_id).unlink(missing_ok=True)
        removed.append(profile.profile_id)
    return {"root": str(root.resolve()), "removed_profiles": removed}


def persistent_status(root: Path) -> dict[str, Any]:
    """Return local runtime/attachment status for project profiles."""
    profiles = profiles_for_root(root)
    return {
        "root": str(root.resolve()),
        "installed": bool(profiles),
        "profiles": [
            {
                **profile.to_dict(),
                "running": proxy_alive(profile),
                "artifact_exists": Path(profile.service_artifact).exists()
                if profile.service_kind != "windows-task"
                else True,
            }
            for profile in profiles
        ],
    }


def run_profile(profile_id: str) -> int:
    """Run one stored profile in the foreground for the native supervisor."""
    profile = load_profile(profile_id)
    run_provider_proxy(
        ProviderProxyConfig(
            root=Path(profile.root),
            upstream=profile.upstream,
            provider=profile.provider,
            bind="127.0.0.1",
            port=profile.port,
            instance_id=_runtime_instance_id(profile),
        )
    )
    return 0
