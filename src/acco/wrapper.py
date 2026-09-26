"""Low-friction provider-proxy wrapper for coding agents and arbitrary CLIs."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class ProviderDefaults:
    """Describe one provider's upstream and client environment contract."""

    upstream: str
    base_url_env: str
    credential_envs: tuple[str, ...]


PROVIDERS = {
    "anthropic": ProviderDefaults(
        "https://api.anthropic.com",
        "ANTHROPIC_BASE_URL",
        ("ANTHROPIC_API_KEY",),
    ),
    "openai": ProviderDefaults(
        "https://api.openai.com",
        "OPENAI_BASE_URL",
        ("OPENAI_API_KEY",),
    ),
    "gemini": ProviderDefaults(
        "https://generativelanguage.googleapis.com",
        "GOOGLE_GEMINI_BASE_URL",
        ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    ),
}


@dataclass(frozen=True)
class HostPreset:
    """Describe one coding agent with an unambiguous provider."""

    executable: str
    provider: str


PRESETS = {
    "claude": HostPreset("claude", "anthropic"),
    "codex": HostPreset("codex", "openai"),
    "gemini": HostPreset("gemini", "gemini"),
}


@dataclass(frozen=True)
class WrapPlan:
    """A deterministic launch plan that can be inspected before execution."""

    agent: str
    executable: str
    provider: str
    upstream: str
    base_url_env: str
    bind: str
    port: int
    argv: tuple[str, ...]
    provider_source: str = "explicit"

    @property
    def local_base_url(self) -> str:
        """Return the provider-compatible local proxy base URL."""
        base = f"http://{self.bind}:{self.port}"
        return base + "/v1" if self.provider == "openai" else base

    def to_dict(self) -> dict:
        """Return a JSON-safe description of the launch plan."""
        return {
            "agent": self.agent,
            "executable": self.executable,
            "provider": self.provider,
            "provider_source": self.provider_source,
            "upstream": self.upstream,
            "base_url_env": self.base_url_env,
            "local_base_url": self.local_base_url,
            "argv": list(self.argv),
        }


def _agent_key(value: str) -> str:
    """Return a platform-neutral executable name for preset detection."""
    name = value.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _provider_from_model(value: str) -> str | None:
    """Infer a provider from one explicit model hint when it is unambiguous."""
    model = value.strip().lower()
    if not model:
        return None
    if "claude" in model or model.startswith("anthropic/"):
        return "anthropic"
    if "gemini" in model or model.startswith("google/"):
        return "gemini"
    openai_markers = (
        "gpt-",
        "openai/",
        "codex",
        "o1",
        "o3",
        "o4",
    )
    if model.startswith(openai_markers) or "/gpt-" in model:
        return "openai"
    return None


def _model_provider_hint(agent_args: list[str]) -> str | None:
    """Read common CLI model flags without consuming child arguments."""
    for index, item in enumerate(agent_args):
        if item.startswith("--model="):
            return _provider_from_model(item.split("=", 1)[1])
        if item in {"--model", "-m"} and index + 1 < len(agent_args):
            return _provider_from_model(agent_args[index + 1])
    return None


def _providers_from_env(env: dict[str, str], *, credentials: bool) -> set[str]:
    """Return providers evidenced by configured base URLs or credentials."""
    found: set[str] = set()
    for provider, defaults in PROVIDERS.items():
        names = defaults.credential_envs if credentials else (defaults.base_url_env,)
        if any(str(env.get(name, "")).strip() for name in names):
            found.add(provider)
    return found


def infer_wrap_provider(
    agent: str,
    agent_args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Infer the provider conservatively for a zero-config wrapped command.

    Precedence is: known executable, explicit model hint, one configured base
    URL, then one configured credential family. Ambiguous environments fail
    closed and ask the caller to pass an explicit provider.
    """
    environ = dict(os.environ if env is None else env)
    preset = PRESETS.get(_agent_key(agent))
    if preset is not None:
        return preset.provider, "preset"

    hinted = _model_provider_hint(agent_args)
    if hinted is not None:
        return hinted, "model"

    base_candidates = _providers_from_env(environ, credentials=False)
    if len(base_candidates) == 1:
        return next(iter(base_candidates)), "base-url-env"
    if len(base_candidates) > 1:
        raise ValueError(
            "multiple provider base URLs are configured; pass --provider "
            "or a recognizable --model to select one"
        )

    credential_candidates = _providers_from_env(environ, credentials=True)
    if len(credential_candidates) == 1:
        return next(iter(credential_candidates)), "credential-env"
    if len(credential_candidates) > 1:
        raise ValueError(
            "multiple provider credential families are configured; pass --provider "
            "or a recognizable --model to select one"
        )
    raise ValueError(
        f"cannot infer provider for {agent!r}; pass --provider "
        "anthropic|openai|gemini, set one provider API key/base URL, "
        "or pass a recognizable --model"
    )


def _upstream_from_existing_base(provider: str, value: str) -> str:
    """Convert an SDK base URL into the proxy's upstream origin/base."""
    raw = value.strip()
    if not raw:
        return PROVIDERS[provider].upstream
    parsed = urlsplit(raw)
    if provider == "openai" and parsed.path.rstrip("/").endswith("/v1"):
        path = parsed.path.rstrip("/")[:-3] or ""
        return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))
    return raw.rstrip("/")


def _free_port(bind: str) -> int:
    """Reserve an ephemeral loopback port long enough to choose a launch port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind((bind, 0))
        return int(handle.getsockname()[1])


def build_wrap_plan(
    agent: str,
    agent_args: list[str],
    *,
    bind: str = "127.0.0.1",
    port: int = 0,
    provider: str | None = None,
    upstream: str | None = None,
    base_url_env: str | None = None,
    executable: str | None = None,
    env: dict[str, str] | None = None,
) -> WrapPlan:
    """Build a wrapper plan without launching a provider or child process."""
    environ = dict(os.environ if env is None else env)
    agent_key = _agent_key(agent)
    preset = PRESETS.get(agent_key)

    if provider is None:
        selected_provider, provider_source = infer_wrap_provider(
            agent,
            agent_args,
            env=environ,
        )
    else:
        selected_provider = provider.strip().lower()
        provider_source = "explicit"
    if selected_provider not in PROVIDERS:
        raise ValueError(
            "wrap provider must be one of: " + ", ".join(sorted(PROVIDERS))
        )

    defaults = PROVIDERS[selected_provider]
    selected_env = base_url_env or defaults.base_url_env
    existing_base = environ.get(selected_env, "")
    selected_upstream = upstream or _upstream_from_existing_base(
        selected_provider,
        existing_base,
    )
    if executable:
        selected_executable = executable
    elif preset is not None and agent_key == agent.lower():
        selected_executable = preset.executable
    else:
        selected_executable = agent

    selected_port = port or _free_port(bind)
    if selected_port <= 0 or selected_port > 65535:
        raise ValueError("port must be between 1 and 65535")
    return WrapPlan(
        agent=agent_key,
        executable=selected_executable,
        provider=selected_provider,
        provider_source=provider_source,
        upstream=selected_upstream,
        base_url_env=selected_env,
        bind=bind,
        port=selected_port,
        argv=tuple(agent_args),
    )


def _wait_for_proxy(bind: str, port: int, timeout: float = 5.0) -> None:
    """Wait for the local proxy socket without sending provider traffic."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((bind, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("ACCO provider proxy did not become ready")


def _provider_proxy_argv(root: Path, plan: WrapPlan, model_routing: str) -> list[str]:
    """Build the provider-proxy command for Python and frozen executables."""
    entry = (
        [sys.executable]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "acco.entry"]
    )
    return [
        *entry,
        "provider-proxy",
        str(root.resolve()),
        "--upstream",
        plan.upstream,
        "--provider",
        plan.provider,
        "--bind",
        plan.bind,
        "--port",
        str(plan.port),
        "--model-routing",
        model_routing,
    ]


def _child_env(plan: WrapPlan, proxy_url: str | None = None) -> dict[str, str]:
    """Return the child environment with only the selected provider redirected."""
    env = os.environ.copy()
    env[plan.base_url_env] = proxy_url or plan.local_base_url
    env["ACCO_WRAPPED"] = "1"
    env["ACCO_WRAP_PROVIDER"] = plan.provider
    return env


def run_wrap(
    root: Path,
    plan: WrapPlan,
    *,
    model_routing: str = "off",
    proxy_url: str | None = None,
) -> int:
    """Launch a command through an ephemeral or already-running ACCO proxy."""
    if os.environ.get("ACCO_WRAPPED") == "1":
        raise RuntimeError("nested acco wrap detected; launch the child command directly")

    executable = shutil.which(plan.executable)
    if executable is None:
        raise FileNotFoundError(f"agent executable not found: {plan.executable}")

    if proxy_url:
        completed = subprocess.run(
            [executable, *plan.argv],
            env=_child_env(plan, proxy_url),
            cwd=root,
            check=False,
        )
        return int(completed.returncode)

    proxy_argv = _provider_proxy_argv(root, plan, model_routing)
    proxy = subprocess.Popen(proxy_argv)
    try:
        _wait_for_proxy(plan.bind, plan.port)
        completed = subprocess.run(
            [executable, *plan.argv],
            env=_child_env(plan),
            cwd=root,
            check=False,
        )
        return int(completed.returncode)
    finally:
        proxy.terminate()
        try:
            proxy.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proxy.kill()
            proxy.wait(timeout=2)
