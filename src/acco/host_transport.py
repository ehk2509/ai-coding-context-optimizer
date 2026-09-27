"""Host transport capability registry for provider interception policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HostTransport:
    """Describe the supported provider-transport surfaces for one coding host."""

    host: str
    provider: str | None
    foreground: str
    persistent: str
    persistent_mode: str | None
    requires_model: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        """Return a JSON-safe host transport record."""
        return asdict(self)


HOST_TRANSPORTS: dict[str, HostTransport] = {
    "claude": HostTransport(
        host="claude",
        provider="anthropic",
        foreground="automatic",
        persistent="automatic",
        persistent_mode="project-config",
        note="Project-scoped ANTHROPIC_BASE_URL ownership is supported.",
    ),
    "codex": HostTransport(
        host="codex",
        provider="openai",
        foreground="automatic",
        persistent="automatic",
        persistent_mode="project-config",
        note="Project-scoped model provider routing is supported.",
    ),
    "copilot": HostTransport(
        host="copilot",
        provider=None,
        foreground="automatic",
        persistent="environment-only",
        persistent_mode=None,
        requires_model=True,
        note=(
            "Copilot CLI documents BYOK provider environment variables, but ACCO "
            "does not rewrite user shell startup files to persist them."
        ),
    ),
    "openclaw": HostTransport(
        host="openclaw",
        provider=None,
        foreground="automatic",
        persistent="environment-only",
        persistent_mode=None,
        note=(
            "OpenClaw foreground wrapping uses a temporary documented config-path "
            "overlay; ACCO does not globally replace the user's active config."
        ),
    ),
    "cursor": HostTransport(
        host="cursor",
        provider="openai",
        foreground="manual-setting",
        persistent="manual-setting",
        persistent_mode=None,
        note=(
            "Cursor exposes the OpenAI BYOK base URL in Settings but no stable "
            "machine-writable provider-setting contract ACCO is willing to own."
        ),
    ),
    "gemini": HostTransport(
        host="gemini",
        provider="gemini",
        foreground="automatic",
        persistent="unsupported",
        persistent_mode=None,
        note="Foreground provider wrapping is supported; durable host routing is not.",
    ),
}


def transport_for(host: str) -> HostTransport:
    """Return one normalized host transport record."""
    key = host.strip().lower().replace("_", "-")
    aliases = {
        "claude-code": "claude",
        "github-copilot": "copilot",
        "copilot-cli": "copilot",
        "cursor-agent": "cursor",
        "gemini-cli": "gemini",
    }
    key = aliases.get(key, key)
    try:
        return HOST_TRANSPORTS[key]
    except KeyError as exc:
        raise ValueError(f"unknown host transport: {host}") from exc


def persistent_hosts() -> tuple[str, ...]:
    """Return hosts for which ACCO owns a durable automatic routing surface."""
    return tuple(
        sorted(
            record.host
            for record in HOST_TRANSPORTS.values()
            if record.persistent == "automatic"
        )
    )


def persistent_provider_map() -> dict[str, str]:
    """Return durable hosts mapped to their single provider."""
    result: dict[str, str] = {}
    for host in persistent_hosts():
        record = HOST_TRANSPORTS[host]
        if record.provider is None:
            raise RuntimeError(f"persistent host lacks provider: {host}")
        result[host] = record.provider
    return result


def transport_report(host: str | None = None) -> dict:
    """Return one host or the complete transport capability registry."""
    if host:
        record = transport_for(host)
        return {"host": record.to_dict()}
    return {
        "hosts": {
            name: record.to_dict()
            for name, record in sorted(HOST_TRANSPORTS.items())
        }
    }
