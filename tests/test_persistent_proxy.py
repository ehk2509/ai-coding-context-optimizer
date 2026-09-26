"""Tests for persistent background provider proxy installation."""

from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading
from urllib.request import urlopen

import pytest

from acco import persistent_proxy
from acco.provider_proxy import ProviderProxyConfig, _handler_factory
from acco.persistent_proxy import (
    PersistentProxyProfile,
    attach_claude,
    attach_codex,
    detach_claude,
    detach_codex,
    install_persistent_profiles,
    install_service,
    profiles_for_root,
    render_service_artifact,
    run_profile,
    start_service,
    stop_service,
    uninstall_persistent_profiles,
)


def _ok_runner(calls):
    def run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return subprocess.CompletedProcess(argv, 0, "", "")
    return run


def _profile(root: Path, provider: str, port: int, host: str) -> PersistentProxyProfile:
    profile_id = persistent_proxy._profile_id(root, provider)
    return PersistentProxyProfile(
        profile_id=profile_id,
        root=str(root.resolve()),
        provider=provider,
        upstream=persistent_proxy.PROVIDERS[provider].upstream,
        port=port,
        hosts=(host,),
        service_kind="systemd-user",
        service_artifact=str(
            root / f"acco-proxy-{profile_id}.service"
        ),
    )


def test_service_artifacts_are_user_scoped_and_credential_free(tmp_path, monkeypatch):
    """Native service definitions should store only profile identity and executable."""
    monkeypatch.setattr(
        persistent_proxy,
        "_resolve_acco_command",
        lambda: ["/opt/acco/bin/acco"],
    )
    monkeypatch.setattr(
        persistent_proxy,
        "state_dir",
        lambda: tmp_path / "state",
    )

    linux_path, linux = render_service_artifact(
        "abc123",
        kind="systemd-user",
        home=tmp_path,
    )
    assert linux_path == tmp_path / ".config/systemd/user/acco-proxy-abc123.service"
    expected_state = persistent_proxy._systemd_escape_arg(
        str(tmp_path / "state")
    )
    assert (
        "ExecStart=/opt/acco/bin/acco proxy-run abc123 --state-dir "
        + expected_state
    ) in linux
    assert "API_KEY" not in linux

    mac_path, plist = render_service_artifact(
        "abc123",
        kind="launchd-user",
        home=tmp_path,
    )
    assert mac_path == tmp_path / "Library/LaunchAgents/com.acco.proxy.abc123.plist"
    assert "<string>proxy-run</string><string>abc123</string>" in plist
    assert "<string>--state-dir</string>" in plist
    assert f"<string>{tmp_path / 'state'}</string>" in plist
    assert "API_KEY" not in plist

    windows_path, windows = render_service_artifact(
        "abc123",
        kind="windows-task",
        home=tmp_path,
    )
    assert windows is None
    assert windows_path.name == "abc123.json"


def test_claude_attachment_is_owned_reversible_and_preserves_other_settings(tmp_path):
    """Claude attachment should mutate only ACCO-owned env keys."""
    root = tmp_path / "repo"
    root.mkdir()
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "env": {"OTHER": "keep"},
                "permissions": {"allow": ["Read"]},
            }
        ),
        encoding="utf-8",
    )
    profile = _profile(root, "anthropic", 19021, "claude")

    attach_claude(profile)
    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert payload["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:19021"
    assert payload["env"]["ACCO_PERSISTENT_PROXY_PROFILE"] == profile.profile_id
    assert payload["env"]["OTHER"] == "keep"
    assert payload["permissions"] == {"allow": ["Read"]}

    detach_claude(profile)
    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert payload["env"] == {"OTHER": "keep"}
    assert payload["permissions"] == {"allow": ["Read"]}


def test_claude_attachment_refuses_user_base_url(tmp_path):
    """Persistent install must not silently replace a user's gateway."""
    root = tmp_path / "repo"
    root.mkdir()
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://gateway.example"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="user-managed Claude"):
        attach_claude(_profile(root, "anthropic", 19022, "claude"))

    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert payload["env"]["ANTHROPIC_BASE_URL"] == "https://gateway.example"


def test_codex_attachment_preserves_unrelated_toml_and_oauth_mode(tmp_path):
    """Codex routing should be marker-owned and retain unrelated config."""
    root = tmp_path / "repo"
    home = tmp_path / "home"
    root.mkdir()
    codex_dir = home / ".codex"
    codex_dir.mkdir(parents=True)
    config = root / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        'model = "gpt-5.6-sol"\n\n[features]\nweb_search = true\n',
        encoding="utf-8",
    )
    (codex_dir / "auth.json").write_text(
        json.dumps({"auth_mode": "chatgpt"}),
        encoding="utf-8",
    )
    profile = _profile(root, "openai", 19023, "codex")

    attach_codex(profile, home=home)
    first = config.read_text(encoding="utf-8")
    attach_codex(profile, home=home)
    second = config.read_text(encoding="utf-8")

    assert first == second
    assert 'model = "gpt-5.6-sol"' in second
    assert "[features]" in second
    assert "web_search = true" in second
    assert second.count("[model_providers.acco]") == 1
    assert f'base_url = "http://127.0.0.1:19023/v1"' in second
    assert "supports_websockets = false" in second
    assert "requires_openai_auth = true" in second

    detach_codex(profile, home=home)
    cleaned = config.read_text(encoding="utf-8")
    assert "ACCO persistent proxy" not in cleaned
    assert "[model_providers.acco]" not in cleaned
    assert 'model = "gpt-5.6-sol"' in cleaned
    assert "[features]" in cleaned


def test_codex_attachment_refuses_existing_root_routing(tmp_path):
    """ACCO must not take over a user's active Codex provider selection."""
    root = tmp_path / "repo"
    home = tmp_path / "home"
    root.mkdir()
    config = root / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        'model_provider = "company"\n\n[model_providers.company]\n'
        'base_url = "https://gateway.example/v1"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="user-managed Codex root routing"):
        attach_codex(_profile(root, "openai", 19024, "codex"), home=home)

    assert 'model_provider = "company"' in config.read_text(encoding="utf-8")


def test_install_two_provider_profiles_and_uninstall_transactionally(
    tmp_path,
    monkeypatch,
):
    """Claude and Codex should get separate stable provider listeners."""
    root = tmp_path / "repo"
    home = tmp_path / "home"
    state = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("ACCO_STATE_DIR", str(state))
    monkeypatch.setattr(persistent_proxy, "_wait_profile_ready", lambda _profile: True)
    monkeypatch.setattr(
        persistent_proxy,
        "_resolve_acco_command",
        lambda: ["/opt/acco/bin/acco"],
    )
    calls = []
    runner = _ok_runner(calls)

    result = install_persistent_profiles(
        root,
        ("claude", "codex"),
        ports={"anthropic": 19025, "openai": 19026},
        kind="systemd-user",
        home=home,
        runner=runner,
    )

    assert result["hosts"] == ["claude", "codex"]
    profiles = profiles_for_root(root)
    assert {item.provider for item in profiles} == {"anthropic", "openai"}
    assert {item.port for item in profiles} == {19025, 19026}
    settings = json.loads(
        (root / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert settings["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:19025"
    codex = (root / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert 'base_url = "http://127.0.0.1:19026/v1"' in codex

    service_calls = [argv for argv, _kwargs in calls]
    assert ["systemctl", "--user", "daemon-reload"] in service_calls
    assert sum(
        1
        for argv in service_calls
        if argv[:3] == ["systemctl", "--user", "enable"]
    ) == 2
    assert sum(
        1
        for argv in service_calls
        if argv[:3] == ["systemctl", "--user", "restart"]
    ) == 2

    removed = uninstall_persistent_profiles(
        root,
        home=home,
        runner=runner,
    )
    assert len(removed["removed_profiles"]) == 2
    assert profiles_for_root(root) == ()
    settings = json.loads(
        (root / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert "ANTHROPIC_BASE_URL" not in settings.get("env", {})
    assert "[model_providers.acco]" not in (
        root / ".codex" / "config.toml"
    ).read_text(encoding="utf-8")


def test_install_rolls_back_first_provider_when_second_service_fails(
    tmp_path,
    monkeypatch,
):
    """Partial multi-provider installation must not strand host routing."""
    root = tmp_path / "repo"
    home = tmp_path / "home"
    state = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("ACCO_STATE_DIR", str(state))
    monkeypatch.setattr(persistent_proxy, "_wait_profile_ready", lambda _profile: True)
    monkeypatch.setattr(
        persistent_proxy,
        "_resolve_acco_command",
        lambda: ["/opt/acco/bin/acco"],
    )
    enable_count = 0

    def runner(argv, **kwargs):
        nonlocal enable_count
        if argv[:3] == ["systemctl", "--user", "restart"]:
            enable_count += 1
            if enable_count == 2:
                raise subprocess.CalledProcessError(
                    1,
                    argv,
                    stderr="synthetic second-provider failure",
                )
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.raises(subprocess.CalledProcessError):
        install_persistent_profiles(
            root,
            ("claude", "codex"),
            ports={"anthropic": 19027, "openai": 19028},
            kind="systemd-user",
            home=home,
            runner=runner,
        )

    assert profiles_for_root(root) == ()
    settings_path = root / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "ANTHROPIC_BASE_URL" not in settings.get("env", {})
    codex = root / ".codex" / "config.toml"
    assert not codex.exists() or "[model_providers.acco]" not in codex.read_text(
        encoding="utf-8"
    )


def test_provider_proxy_health_reports_content_free_instance_identity(tmp_path):
    """Persistent readiness must distinguish the expected ACCO listener from a random port."""
    root = tmp_path / "repo"
    root.mkdir()
    config = ProviderProxyConfig(
        root=root,
        upstream="https://api.openai.com",
        provider="openai",
        bind="127.0.0.1",
        port=19029,
        instance_id="profile-abc",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_factory(config))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/__acco/health") as response:
            payload = json.loads(response.read())
        assert payload["ok"] is True
        assert payload["provider"] == "openai"
        assert payload["instance_id"] == "profile-abc"
        assert len(payload["root_fingerprint"]) == 16
        assert str(root) not in json.dumps(payload)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_uninstall_refuses_dangling_claude_local_route(tmp_path, monkeypatch):
    """A damaged ownership marker must not let uninstall strand Claude."""
    root = tmp_path / "repo"
    state = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("ACCO_STATE_DIR", str(state))
    profile = _profile(root, "anthropic", 19030, "claude")
    persistent_proxy._save_profile(profile)

    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps({"env": {"ANTHROPIC_BASE_URL": profile.local_base_url}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ownership marker is missing"):
        uninstall_persistent_profiles(
            root,
            runner=_ok_runner([]),
        )

    assert profiles_for_root(root) == (profile,)
    assert json.loads(settings.read_text(encoding="utf-8"))["env"][
        "ANTHROPIC_BASE_URL"
    ] == profile.local_base_url


def test_uninstall_refuses_dangling_codex_local_route(tmp_path, monkeypatch):
    """A markerless Codex route must keep its service until ownership is resolved."""
    root = tmp_path / "repo"
    state = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("ACCO_STATE_DIR", str(state))
    profile = _profile(root, "openai", 19031, "codex")
    persistent_proxy._save_profile(profile)

    config = root / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        'model_provider = "acco"\n'
        f'openai_base_url = "{profile.local_base_url}"\n\n'
        "[model_providers.acco]\n"
        f'base_url = "{profile.local_base_url}"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ownership markers are missing"):
        uninstall_persistent_profiles(
            root,
            runner=_ok_runner([]),
        )

    assert profiles_for_root(root) == (profile,)
    assert profile.local_base_url in config.read_text(encoding="utf-8")


def test_codex_attachment_refuses_invalid_existing_toml(tmp_path):
    """Persistent routing must not write through an already-invalid Codex config."""
    root = tmp_path / "repo"
    home = tmp_path / "home"
    root.mkdir()
    config = root / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[features\ninvalid = true\n", encoding="utf-8")
    before = config.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="invalid Codex TOML"):
        attach_codex(_profile(root, "openai", 19032, "codex"), home=home)

    assert config.read_text(encoding="utf-8") == before


def test_launchd_stop_boots_out_and_start_rebootstraps(tmp_path, monkeypatch):
    """macOS stop must not use kill with KeepAlive because launchd would restart it."""
    monkeypatch.setattr(
        persistent_proxy.os,
        "getuid",
        lambda: 501,
        raising=False,
    )
    calls = []
    runner = _ok_runner(calls)
    artifact = tmp_path / "Library/LaunchAgents/com.acco.proxy.mac.plist"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("<plist/>", encoding="utf-8")
    profile = PersistentProxyProfile(
        profile_id="mac",
        root=str(tmp_path),
        provider="anthropic",
        upstream="https://api.anthropic.com",
        port=19033,
        hosts=("claude",),
        service_kind="launchd-user",
        service_artifact=str(artifact),
    )

    stop_service(profile, runner=runner)
    start_service(profile, runner=runner)

    argv = [item[0] for item in calls]
    assert [
        "launchctl",
        "bootout",
        "gui/501",
        str(artifact),
    ] in argv
    assert [
        "launchctl",
        "bootstrap",
        "gui/501",
        str(artifact),
    ] in argv
    assert not any("kill" in command for command in argv)


def test_windows_install_ends_previous_task_before_recreate(tmp_path, monkeypatch):
    """Windows reconfiguration should restart rather than leave stale task runtime."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(
        persistent_proxy,
        "_resolve_acco_command",
        lambda: [r"C:\Tools\acco.exe"],
    )
    calls = []
    install_service(
        "winprofile",
        kind="windows-task",
        home=tmp_path,
        runner=_ok_runner(calls),
    )
    argv = [item[0] for item in calls]

    assert argv[0] == ["schtasks", "/End", "/TN", "ACCO Proxy winprofile"]
    assert argv[1][:3] == ["schtasks", "/Create", "/TN"]
    assert "--state-dir" in argv[1][argv[1].index("/TR") + 1]
    assert argv[2] == ["schtasks", "/Run", "/TN", "ACCO Proxy winprofile"]


def test_persistent_runner_uses_project_provider_settings(tmp_path, monkeypatch):
    """Background runtime must match foreground provider-proxy project policy."""
    root = tmp_path / "repo"
    state = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("ACCO_STATE_DIR", str(state))
    (root / ".acco.toml").write_text(
        "[provider]\n"
        "prefix_tracking = false\n"
        "history_dedup = false\n"
        'model_routing = "observe"\n'
        'routing_calibration_file = "custom-routing.json"\n'
        "routing_min_savings = 0.17\n",
        encoding="utf-8",
    )
    profile = _profile(root, "anthropic", 19034, "claude")
    persistent_proxy._save_profile(profile)
    captured = {}

    def fake_run(config):
        captured["config"] = config

    monkeypatch.setattr(persistent_proxy, "run_provider_proxy", fake_run)

    assert run_profile(profile.profile_id) == 0
    config = captured["config"]
    assert config.prefix_tracking is False
    assert config.deduplicate_history is False
    assert config.model_routing_mode == "observe"
    assert config.model_routing_calibration_file == "custom-routing.json"
    assert config.model_routing_min_savings == 0.17
    assert config.instance_id == persistent_proxy._runtime_instance_id(profile)


def test_stopped_profile_port_remains_reserved_for_other_projects(
    tmp_path,
    monkeypatch,
):
    """Stable ports must not be reused just because an existing proxy is stopped."""
    state = tmp_path / "state"
    root_one = tmp_path / "one"
    root_two = tmp_path / "two"
    root_one.mkdir()
    root_two.mkdir()
    monkeypatch.setenv("ACCO_STATE_DIR", str(state))

    first = _profile(root_one, "anthropic", 19035, "claude")
    persistent_proxy._save_profile(first)
    monkeypatch.setattr(persistent_proxy, "_wait_profile_ready", lambda _profile: True)
    monkeypatch.setattr(
        persistent_proxy,
        "_resolve_acco_command",
        lambda: ["/opt/acco/bin/acco"],
    )

    with pytest.raises(ValueError, match="already reserved"):
        install_persistent_profiles(
            root_two,
            ("claude",),
            ports={"anthropic": 19035},
            kind="systemd-user",
            home=tmp_path / "home",
            runner=_ok_runner([]),
        )

    assert profiles_for_root(root_two) == ()


def test_new_profile_allocator_skips_reserved_stopped_port(tmp_path, monkeypatch):
    """Automatic allocation should retry when the OS offers a persisted port."""
    state = tmp_path / "state"
    root_one = tmp_path / "one"
    root_two = tmp_path / "two"
    root_one.mkdir()
    root_two.mkdir()
    monkeypatch.setenv("ACCO_STATE_DIR", str(state))
    persistent_proxy._save_profile(
        _profile(root_one, "anthropic", 19036, "claude")
    )

    offered = iter([19036, 19037])

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def bind(self, _address):
            return None

        def getsockname(self):
            return ("127.0.0.1", next(offered))

    monkeypatch.setattr(persistent_proxy.socket, "socket", lambda *_a, **_k: FakeSocket())

    assert persistent_proxy._free_port(excluded={19036}) == 19037


def test_service_command_preserves_stable_launcher_symlink(tmp_path, monkeypatch):
    """Persistent services should survive package upgrades that retarget a launcher."""
    if persistent_proxy.os.name == "nt":
        pytest.skip("symlink creation is not reliably available on Windows CI")
    target = tmp_path / "versions" / "acco-1.20"
    target.parent.mkdir()
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher = tmp_path / "bin" / "acco"
    launcher.parent.mkdir()
    launcher.symlink_to(target)
    monkeypatch.setattr(
        persistent_proxy.shutil,
        "which",
        lambda _name: str(launcher),
    )

    command = persistent_proxy._resolve_acco_command()

    assert command == [str(launcher.absolute())]
    assert command[0] != str(target.resolve())
