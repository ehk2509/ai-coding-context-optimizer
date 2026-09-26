"""Host-specific provider-boundary adapters for ACCO wrap."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


@dataclass(frozen=True)
class PreparedHostEnvironment:
    """Child environment plus temporary artifacts owned by one wrap session."""

    env: dict[str, str]
    cleanup_paths: tuple[Path, ...] = ()


def copilot_provider_hint(
    args: list[str],
    env: dict[str, str],
) -> tuple[str | None, str | None]:
    """Return ACCO provider plus Copilot provider type when documented hints exist."""
    raw_type = str(env.get("COPILOT_PROVIDER_TYPE", "")).strip().lower()
    if raw_type:
        if raw_type == "anthropic":
            return "anthropic", "anthropic"
        if raw_type in {"openai", "azure"}:
            return "openai", raw_type
        raise ValueError(
            "unsupported COPILOT_PROVIDER_TYPE for ACCO wrap: "
            f"{raw_type!r}; supported: openai, azure, anthropic"
        )

    model = str(env.get("COPILOT_MODEL", "")).strip()
    for index, item in enumerate(args):
        if item.startswith("--model="):
            model = item.split("=", 1)[1]
            break
        if item in {"--model", "-m"} and index + 1 < len(args):
            model = args[index + 1]
            break
    lowered = model.lower()
    if "claude" in lowered or lowered.startswith("anthropic/"):
        return "anthropic", "anthropic"
    if (
        lowered.startswith(("gpt-", "openai/", "o1", "o3", "o4", "codex"))
        or "/gpt-" in lowered
    ):
        return "openai", "openai"

    if str(env.get("COPILOT_PROVIDER_BASE_URL", "")).strip():
        return "openai", "openai"
    return None, None


def prepare_copilot_env(
    base_env: dict[str, str],
    *,
    provider: str,
    proxy_url: str,
    args: tuple[str, ...] = (),
) -> dict[str, str]:
    """Route Copilot CLI BYOK traffic through ACCO using documented env vars."""
    env = dict(base_env)
    if provider not in {"openai", "anthropic"}:
        raise ValueError(
            "Copilot CLI BYOK wrap supports OpenAI-compatible/Azure and Anthropic "
            "providers; Gemini is not a documented Copilot provider type"
        )
    existing_type = str(env.get("COPILOT_PROVIDER_TYPE", "")).strip().lower()
    if provider == "anthropic":
        env["COPILOT_PROVIDER_TYPE"] = "anthropic"
    elif existing_type != "azure":
        env["COPILOT_PROVIDER_TYPE"] = "openai"
    env["COPILOT_PROVIDER_BASE_URL"] = proxy_url

    if not str(env.get("COPILOT_PROVIDER_API_KEY", "")).strip():
        source_key = (
            env.get("ANTHROPIC_API_KEY")
            if provider == "anthropic"
            else env.get("OPENAI_API_KEY")
        )
        if source_key:
            env["COPILOT_PROVIDER_API_KEY"] = source_key

    model_present = bool(str(env.get("COPILOT_MODEL", "")).strip())
    if not model_present:
        for index, item in enumerate(args):
            if item.startswith("--model="):
                model_present = bool(item.split("=", 1)[1].strip())
                break
            if item in {"--model", "-m"} and index + 1 < len(args):
                model_present = bool(str(args[index + 1]).strip())
                break
    if not model_present:
        raise ValueError(
            "Copilot CLI custom-provider mode requires COPILOT_MODEL or --model; "
            "set one before wrapping"
        )
    return env


def cursor_setup_lines(proxy_url: str, provider: str) -> tuple[str, ...]:
    """Return documented Cursor BYOK setup guidance without editing private state."""
    if provider != "openai":
        raise ValueError(
            "Cursor currently documents a custom base-URL override for its OpenAI "
            "BYOK path; ACCO will not rewrite undocumented provider state"
        )
    return (
        "Cursor requires one manual BYOK setting for provider interception.",
        "Open Cursor Settings > Models > API Keys.",
        "Enable OpenAI API Key and Override OpenAI Base URL.",
        f"Set Override OpenAI Base URL to: {proxy_url}",
        "Keep this ACCO proxy session running while using Cursor Chat/Agent.",
        "Cursor Tab completion is not redirected by the BYOK base-URL override.",
    )


def _openclaw_config_path(env: dict[str, str]) -> Path:
    """Return the documented active OpenClaw config path."""
    override = str(env.get("OPENCLAW_CONFIG_PATH", "")).strip()
    if override:
        return Path(override).expanduser()
    home = Path(
        env.get("OPENCLAW_HOME")
        or env.get("USERPROFILE")
        or env.get("HOME")
        or Path.home()
    ).expanduser()
    state = str(env.get("OPENCLAW_STATE_DIR", "")).strip()
    state_dir = Path(state).expanduser() if state else home / ".openclaw"
    return state_dir / "openclaw.json"


def _run_json(
    argv: list[str],
    *,
    env: dict[str, str],
) -> Any:
    """Run one read-only host command and parse its JSON response."""
    completed = subprocess.run(
        argv,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "command failed").strip()
        raise ValueError(f"{' '.join(argv[:3])} failed: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{' '.join(argv[:3])} did not return valid JSON"
        ) from exc


def _openclaw_primary_model(executable: str, env: dict[str, str]) -> tuple[str, Any]:
    """Read the active OpenClaw default model through its documented config CLI."""
    value = _run_json(
        [executable, "config", "get", "agents.defaults.model", "--json"],
        env=env,
    )
    if isinstance(value, str):
        primary = value
    elif isinstance(value, dict):
        primary = value.get("primary")
    else:
        primary = None
    if not isinstance(primary, str) or "/" not in primary:
        raise ValueError(
            "OpenClaw wrap requires a configured provider/model default; "
            "set one with openclaw models set first"
        )
    return primary, value


def _openclaw_rows(payload: Any) -> list[dict[str, Any]]:
    """Normalize current OpenClaw model-list JSON shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("models", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(payload.get("key"), str):
        return [payload]
    return []


def _openclaw_model_entry(
    executable: str,
    *,
    provider_id: str,
    model_ref: str,
    env: dict[str, str],
) -> dict[str, Any]:
    """Copy catalog metadata for one active model into an explicit custom row."""
    payload = _run_json(
        [
            executable,
            "models",
            "list",
            "--provider",
            provider_id,
            "--json",
        ],
        env=env,
    )
    rows = _openclaw_rows(payload)
    row = next(
        (
            item for item in rows
            if item.get("key") == model_ref
            or item.get("id") == model_ref.split("/", 1)[1]
        ),
        None,
    )
    if row is None:
        raise ValueError(
            f"OpenClaw model catalog did not expose metadata for {model_ref!r}; "
            "ACCO will not invent context-window/capability values"
        )

    if not isinstance(row.get("contextWindow"), int):
        raise ValueError(
            f"OpenClaw catalog metadata for {model_ref!r} lacks contextWindow; "
            "ACCO will not create a route with guessed token limits"
        )

    model_id = model_ref.split("/", 1)[1]
    entry: dict[str, Any] = {
        "id": model_id,
        "name": str(row.get("name") or model_id),
    }
    for key in ("contextWindow", "contextTokens", "maxTokens", "reasoning", "cost"):
        if key in row and row[key] is not None:
            entry[key] = row[key]
    input_value = row.get("input")
    if isinstance(input_value, list):
        entry["input"] = input_value
    elif isinstance(input_value, str) and input_value:
        entry["input"] = [
            part for part in input_value.replace(",", "+").split("+") if part
        ]
    return entry


def _openclaw_provider_contract(provider_id: str) -> tuple[str, str, tuple[str, ...]]:
    """Map direct OpenClaw API providers to ACCO provider/protocol/key contracts."""
    if provider_id == "openai":
        return "openai", "openai-responses", ("OPENAI_API_KEY",)
    if provider_id == "anthropic":
        return "anthropic", "anthropic-messages", ("ANTHROPIC_API_KEY",)
    if provider_id == "google":
        return "gemini", "google-generative-ai", ("GEMINI_API_KEY", "GOOGLE_API_KEY")
    raise ValueError(
        "OpenClaw automatic wrap currently supports direct API providers "
        "openai/*, anthropic/*, and google/*; OAuth/native/custom provider routes "
        f"such as {provider_id!r} are left untouched"
    )


def inspect_openclaw_provider(
    executable: str,
    *,
    env: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Return ACCO provider and active OpenClaw model ref without mutating config."""
    environ = dict(os.environ if env is None else env)
    model_ref, _ = _openclaw_primary_model(executable, environ)
    provider_id = model_ref.split("/", 1)[0]
    provider, _, _ = _openclaw_provider_contract(provider_id)
    return provider, model_ref


def prepare_openclaw_env(
    executable: str,
    base_env: dict[str, str],
    *,
    provider: str,
    proxy_url: str,
) -> PreparedHostEnvironment:
    """Build an ephemeral OpenClaw config overlay that routes one direct provider."""
    env = dict(base_env)
    model_ref, current_model = _openclaw_primary_model(executable, env)
    provider_id = model_ref.split("/", 1)[0]
    detected_provider, api, key_names = _openclaw_provider_contract(provider_id)
    if provider != detected_provider:
        raise ValueError(
            f"OpenClaw active model {model_ref!r} uses {detected_provider}, "
            f"but ACCO wrap selected {provider}; pass the matching --provider"
        )

    model_entry = _openclaw_model_entry(
        executable,
        provider_id=provider_id,
        model_ref=model_ref,
        env=env,
    )
    key_value = next(
        (
            str(env.get(name))
            for name in key_names
            if str(env.get(name, "")).strip()
        ),
        "",
    )
    if not key_value:
        raise ValueError(
            f"OpenClaw {provider_id} wrap requires an API-key environment "
            f"variable ({', '.join(key_names)}); OAuth/native-runtime credentials "
            "are intentionally not copied or rewritten"
        )

    original = _openclaw_config_path(env)
    original.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=original.parent,
        prefix=".acco-wrap-",
        suffix=".json",
    )
    os.close(fd)
    temp_path = Path(temporary)

    wrapped_ref = f"acco-wrap/{model_entry['id']}"
    if isinstance(current_model, dict):
        wrapped_model: Any = dict(current_model)
        wrapped_model["primary"] = wrapped_ref
    else:
        wrapped_model = {"primary": wrapped_ref}

    overlay: dict[str, Any] = {}
    if original.exists():
        overlay["$include"] = f"./{original.name}"
    overlay["models"] = {
        "mode": "merge",
        "providers": {
            "acco-wrap": {
                "baseUrl": proxy_url,
                "apiKey": "${ACCO_OPENCLAW_PROVIDER_KEY}",
                "api": api,
                "models": [model_entry],
            }
        },
    }
    overlay["agents"] = {"defaults": {"model": wrapped_model}}
    temp_path.write_text(
        json.dumps(overlay, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    env["OPENCLAW_CONFIG_PATH"] = str(temp_path)
    env["ACCO_OPENCLAW_PROVIDER_KEY"] = key_value
    return PreparedHostEnvironment(env=env, cleanup_paths=(temp_path,))
