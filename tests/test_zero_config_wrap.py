"""Tests for zero-config provider wrapping of arbitrary CLI commands."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from acco.command_handlers.everyday import wrap_main
from acco.wrapper import WrapPlan, build_wrap_plan, run_wrap


def test_windows_style_known_executable_uses_preset_without_losing_path():
    """Known executables should be detected across Windows path syntax."""
    plan = build_wrap_plan(
        r"C:\Tools\claude.exe",
        [],
        port=19001,
        env={},
    )

    assert plan.agent == "claude"
    assert plan.executable == r"C:\Tools\claude.exe"
    assert plan.provider == "anthropic"
    assert plan.provider_source == "preset"
    assert plan.base_url_env == "ANTHROPIC_BASE_URL"


def test_model_hint_wins_for_multi_provider_arbitrary_cli():
    """An explicit child model should resolve an otherwise ambiguous environment."""
    plan = build_wrap_plan(
        "aider",
        ["--model", "claude-sonnet-4-5"],
        port=19002,
        env={
            "OPENAI_API_KEY": "openai-secret",
            "ANTHROPIC_API_KEY": "anthropic-secret",
        },
    )

    assert plan.provider == "anthropic"
    assert plan.provider_source == "model"
    assert plan.executable == "aider"


def test_single_credential_enables_zero_config_unknown_command():
    """One provider credential should be enough to wrap an unknown CLI."""
    plan = build_wrap_plan(
        "opencode",
        [],
        port=19003,
        env={"OPENAI_API_KEY": "secret"},
    )

    assert plan.provider == "openai"
    assert plan.provider_source == "credential-env"
    assert plan.upstream == "https://api.openai.com"
    assert plan.local_base_url == "http://127.0.0.1:19003/v1"


def test_existing_openai_gateway_is_preserved_as_upstream():
    """A preconfigured OpenAI base URL should remain the real upstream gateway."""
    plan = build_wrap_plan(
        "custom-agent",
        [],
        port=19004,
        env={"OPENAI_BASE_URL": "https://gateway.example/v1"},
    )

    assert plan.provider == "openai"
    assert plan.provider_source == "base-url-env"
    assert plan.upstream == "https://gateway.example"


def test_ambiguous_environment_fails_closed():
    """Multiple provider families should require an explicit provider selection."""
    with pytest.raises(ValueError, match="multiple provider credential"):
        build_wrap_plan(
            "custom-agent",
            [],
            port=19005,
            env={
                "OPENAI_API_KEY": "one",
                "ANTHROPIC_API_KEY": "two",
            },
        )


def test_existing_proxy_path_injects_environment_and_preserves_exit_code(
    tmp_path,
    monkeypatch,
):
    """Existing-proxy mode should launch only the child and preserve its exit code."""
    monkeypatch.delenv("ACCO_WRAPPED", raising=False)
    monkeypatch.setattr("acco.wrapper.shutil.which", lambda value: f"/bin/{value}")

    captured = {}

    def fake_run(argv, *, env, cwd, check):
        captured.update(argv=argv, env=env, cwd=cwd, check=check)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr("acco.wrapper.subprocess.run", fake_run)

    def fail_popen(*_args, **_kwargs):
        raise AssertionError("existing proxy mode must not start another proxy")

    monkeypatch.setattr("acco.wrapper.subprocess.Popen", fail_popen)

    plan = WrapPlan(
        agent="opencode",
        executable="opencode",
        provider="openai",
        upstream="https://api.openai.com",
        base_url_env="OPENAI_BASE_URL",
        bind="127.0.0.1",
        port=19006,
        argv=("run", "task"),
        provider_source="credential-env",
    )

    code = run_wrap(
        Path(tmp_path),
        plan,
        proxy_url="http://127.0.0.1:8787/v1",
    )

    assert code == 7
    assert captured["argv"] == ["/bin/opencode", "run", "task"]
    assert captured["cwd"] == Path(tmp_path)
    assert captured["check"] is False
    assert captured["env"]["OPENAI_BASE_URL"] == "http://127.0.0.1:8787/v1"
    assert captured["env"]["ACCO_WRAPPED"] == "1"
    assert captured["env"]["ACCO_WRAP_PROVIDER"] == "openai"


def test_nested_wrap_is_rejected(tmp_path, monkeypatch):
    """A wrapped child must not recursively create another proxy chain."""
    monkeypatch.setenv("ACCO_WRAPPED", "1")
    plan = WrapPlan(
        agent="claude",
        executable="claude",
        provider="anthropic",
        upstream="https://api.anthropic.com",
        base_url_env="ANTHROPIC_BASE_URL",
        bind="127.0.0.1",
        port=19007,
        argv=(),
        provider_source="preset",
    )

    with pytest.raises(RuntimeError, match="nested acco wrap"):
        run_wrap(Path(tmp_path), plan)


def test_wrap_cli_accepts_wrapper_flags_after_command_and_child_args(
    monkeypatch,
    capsys,
):
    """Wrapper flags should parse before the separator while child args pass through."""
    monkeypatch.setenv("OPENAI_API_KEY", "secret")

    code = wrap_main(
        [
            "aider",
            "--port",
            "19008",
            "--dry-run",
            "--json",
            "--",
            "--model",
            "gpt-4.1",
            "--yes",
        ]
    )

    assert code == 0
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["provider"] == "openai"
    assert payload["provider_source"] == "model"
    assert payload["local_base_url"] == "http://127.0.0.1:19008/v1"
    assert payload["argv"] == ["--model", "gpt-4.1", "--yes"]
