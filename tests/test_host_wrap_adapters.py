"""Regression tests for host-specific zero-config wrap adapters."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from acco import wrap_adapters
from acco.wrap_adapters import PreparedHostEnvironment, prepare_openclaw_env
from acco.wrapper import build_wrap_plan, run_wrap


def test_copilot_anthropic_uses_documented_provider_environment():
    """Copilot BYOK should route through its own documented base-URL contract."""
    plan = build_wrap_plan(
        "copilot",
        ["--model", "claude-sonnet-5"],
        port=19101,
        env={
            "COPILOT_PROVIDER_TYPE": "anthropic",
            "COPILOT_PROVIDER_BASE_URL": "https://api.anthropic.com",
            "COPILOT_PROVIDER_API_KEY": "secret",
        },
    )

    assert plan.provider == "anthropic"
    assert plan.provider_source == "copilot"
    assert plan.host_adapter == "copilot"
    assert plan.host_provider_type == "anthropic"
    assert plan.base_url_env == "COPILOT_PROVIDER_BASE_URL"
    assert plan.local_base_url == "http://127.0.0.1:19101"


def test_copilot_azure_keeps_root_style_local_base_url():
    """Azure Copilot provider type must not receive OpenAI's synthetic /v1 suffix."""
    plan = build_wrap_plan(
        "copilot",
        ["--model", "gpt-5"],
        port=19102,
        env={
            "COPILOT_PROVIDER_TYPE": "azure",
            "COPILOT_PROVIDER_BASE_URL": "https://example.openai.azure.com",
            "COPILOT_PROVIDER_API_KEY": "secret",
        },
    )

    assert plan.provider == "openai"
    assert plan.host_provider_type == "azure"
    assert plan.upstream == "https://example.openai.azure.com"
    assert plan.local_base_url == "http://127.0.0.1:19102"


def test_copilot_existing_proxy_injects_byok_env_and_preserves_exit(
    tmp_path,
    monkeypatch,
):
    """Copilot adapter should use COPILOT_PROVIDER_* without touching files."""
    monkeypatch.delenv("ACCO_WRAPPED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "standard-secret")
    monkeypatch.delenv("COPILOT_PROVIDER_API_KEY", raising=False)
    monkeypatch.setenv("COPILOT_MODEL", "gpt-5")
    monkeypatch.setattr("acco.wrapper.shutil.which", lambda _value: "/bin/copilot")
    captured = {}

    def fake_run(argv, *, env, cwd, check):
        captured.update(argv=argv, env=env, cwd=cwd, check=check)
        return SimpleNamespace(returncode=9)

    monkeypatch.setattr("acco.wrapper.subprocess.run", fake_run)
    plan = build_wrap_plan(
        "copilot",
        [],
        provider="openai",
        port=19103,
        env={"OPENAI_API_KEY": "standard-secret", "COPILOT_MODEL": "gpt-5"},
    )

    code = run_wrap(
        Path(tmp_path),
        plan,
        proxy_url="http://127.0.0.1:8787/v1",
    )

    assert code == 9
    assert captured["env"]["COPILOT_PROVIDER_BASE_URL"] == "http://127.0.0.1:8787/v1"
    assert captured["env"]["COPILOT_PROVIDER_TYPE"] == "openai"
    assert captured["env"]["COPILOT_PROVIDER_API_KEY"] == "standard-secret"
    assert captured["env"]["ACCO_WRAP_PROVIDER"] == "openai"


def test_cursor_adapter_uses_manual_documented_byok_surface(capsys, tmp_path, monkeypatch):
    """Cursor must print supported BYOK steps rather than mutate private settings."""
    monkeypatch.delenv("ACCO_WRAPPED", raising=False)
    monkeypatch.setattr(
        "acco.wrapper.shutil.which",
        lambda _value: pytest.fail("Cursor manual mode must not require executable lookup"),
    )
    plan = build_wrap_plan("cursor", [], port=19104, env={})

    code = run_wrap(
        Path(tmp_path),
        plan,
        proxy_url="http://127.0.0.1:8787/v1",
    )

    assert code == 0
    output = capsys.readouterr().out
    assert "Cursor Settings > Models > API Keys" in output
    assert "http://127.0.0.1:8787/v1" in output
    assert "Tab completion is not redirected" in output


def test_openclaw_overlay_preserves_original_and_catalog_metadata(tmp_path, monkeypatch):
    """OpenClaw adapter should use an ephemeral sibling include overlay only."""
    home = tmp_path / "home"
    config_dir = home / ".openclaw"
    config_dir.mkdir(parents=True)
    original = config_dir / "openclaw.json"
    original.write_text(
        json.dumps({"agents": {"defaults": {"workspace": "/tmp/work"}}}) + "\n",
        encoding="utf-8",
    )
    before = original.read_bytes()

    def fake_run_json(argv, *, env):
        del env
        if argv[1:4] == ["config", "get", "agents.defaults.model"]:
            return {
                "primary": "openai/gpt-5.6-sol",
                "fallbacks": ["openai/gpt-5.6-luna"],
            }
        if argv[1:4] == ["models", "list", "--provider"]:
            return {
                "models": [
                    {
                        "key": "openai/gpt-5.6-sol",
                        "name": "GPT-5.6 Sol",
                        "input": "text+image",
                        "contextWindow": 400000,
                        "maxTokens": 64000,
                        "agentRuntime": {"id": "openclaw"},
                    }
                ]
            }
        raise AssertionError(argv)

    monkeypatch.setattr(wrap_adapters, "_run_json", fake_run_json)
    prepared = prepare_openclaw_env(
        "openclaw",
        {
            "HOME": str(home),
            "OPENAI_API_KEY": "secret",
        },
        provider="openai",
        proxy_url="http://127.0.0.1:8787/v1",
    )

    temp_path = Path(prepared.env["OPENCLAW_CONFIG_PATH"])
    assert temp_path.parent == config_dir
    assert temp_path != original
    assert original.read_bytes() == before

    overlay = json.loads(temp_path.read_text(encoding="utf-8"))
    assert overlay["$include"] == "./openclaw.json"
    provider = overlay["models"]["providers"]["acco-wrap"]
    assert provider["baseUrl"] == "http://127.0.0.1:8787/v1"
    assert provider["api"] == "openai-responses"
    assert provider["apiKey"] == "$" + "{ACCO_OPENCLAW_PROVIDER_KEY}"
    assert provider["models"][0]["contextWindow"] == 400000
    assert provider["models"][0]["agentRuntime"] == {"id": "openclaw"}
    assert provider["models"][0]["input"] == ["text", "image"]
    assert overlay["agents"]["defaults"]["model"]["fallbacks"] == [
        "openai/gpt-5.6-luna"
    ]
    assert overlay["agents"]["defaults"]["model"]["primary"] == "acco-wrap/gpt-5.6-sol"
    assert prepared.env["ACCO_OPENCLAW_PROVIDER_KEY"] == "secret"
    assert prepared.cleanup_paths == (temp_path,)


def test_openclaw_oauth_native_route_fails_closed(monkeypatch):
    """Native/OAuth provider routes must not be converted into guessed API keys."""
    monkeypatch.setattr(
        wrap_adapters,
        "_run_json",
        lambda _argv, *, env: {"primary": "openai-codex/gpt-5.6-sol"},
    )

    with pytest.raises(ValueError, match="OAuth/native/custom provider routes"):
        wrap_adapters.inspect_openclaw_provider("openclaw", env={})


def test_openclaw_run_removes_ephemeral_overlay(tmp_path, monkeypatch):
    """The wrapper owns and removes its temporary OpenClaw config after exit."""
    monkeypatch.delenv("ACCO_WRAPPED", raising=False)
    monkeypatch.setattr("acco.wrapper.shutil.which", lambda _value: "/bin/openclaw")
    temp = tmp_path / ".acco-wrap-test.json"
    temp.write_text("{}\n", encoding="utf-8")

    def fake_prepare(executable, env, *, provider, proxy_url):
        del executable, provider, proxy_url
        return PreparedHostEnvironment(
            env={**env, "OPENCLAW_CONFIG_PATH": str(temp)},
            cleanup_paths=(temp,),
        )

    monkeypatch.setattr("acco.wrapper.prepare_openclaw_env", fake_prepare)
    monkeypatch.setattr(
        "acco.wrapper.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )

    plan = build_wrap_plan(
        "openclaw",
        [],
        provider="openai",
        port=19105,
        env={"OPENAI_API_KEY": "secret"},
    )
    code = run_wrap(
        Path(tmp_path),
        plan,
        proxy_url="http://127.0.0.1:8787/v1",
    )

    assert code == 0
    assert not temp.exists()


def test_openclaw_openai_without_explicit_runtime_fails_closed(tmp_path, monkeypatch):
    """A custom proxy must not silently change OpenClaw's implicit runtime choice."""
    home = tmp_path / "home"
    (home / ".openclaw").mkdir(parents=True)

    def fake_run_json(argv, *, env):
        del env
        if argv[1] == "config":
            return "openai/gpt-5.6-sol"
        return {
            "models": [
                {
                    "key": "openai/gpt-5.6-sol",
                    "name": "GPT-5.6 Sol",
                    "contextWindow": 400000,
                    "maxTokens": 64000,
                }
            ]
        }

    monkeypatch.setattr(wrap_adapters, "_run_json", fake_run_json)
    with pytest.raises(ValueError, match="implicit Codex/OpenClaw"):
        prepare_openclaw_env(
            "openclaw",
            {"HOME": str(home), "OPENAI_API_KEY": "secret"},
            provider="openai",
            proxy_url="http://127.0.0.1:8787/v1",
        )


def test_openclaw_provider_inference_uses_active_model_before_ambiguous_keys(monkeypatch):
    """Host model selection should disambiguate shells containing several API keys."""
    monkeypatch.setattr("acco.wrapper.shutil.which", lambda _value: "/bin/openclaw")
    monkeypatch.setattr(
        "acco.wrapper.inspect_openclaw_provider",
        lambda _executable, *, env: ("anthropic", "anthropic/claude-sonnet-5"),
    )

    plan = build_wrap_plan(
        "openclaw",
        [],
        port=19106,
        env={
            "OPENAI_API_KEY": "one",
            "ANTHROPIC_API_KEY": "two",
        },
    )

    assert plan.provider == "anthropic"
    assert plan.provider_source == "openclaw-model"
    assert plan.host_adapter == "openclaw"


def test_cursor_manual_bridge_rejects_child_args(tmp_path, monkeypatch):
    """Cursor setup-only mode must not silently discard pass-through arguments."""
    monkeypatch.delenv("ACCO_WRAPPED", raising=False)
    plan = build_wrap_plan(
        "cursor",
        ["--some-cursor-flag"],
        provider="openai",
        port=19107,
        env={},
    )

    with pytest.raises(ValueError, match="child arguments"):
        run_wrap(
            Path(tmp_path),
            plan,
            proxy_url="http://127.0.0.1:8787/v1",
        )
