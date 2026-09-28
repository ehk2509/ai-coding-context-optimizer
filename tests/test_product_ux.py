"""Tests for the frictionless beginner-facing ACCO product UX."""

from __future__ import annotations

import json
from pathlib import Path

import acco.product_ux as product
from acco.entry import main
from acco.integration_setup import setup_integrations, uninstall_integrations


def test_bare_acco_is_a_product_home_screen(tmp_path: Path, capsys):
    """No-argument ACCO should guide setup rather than dump expert commands."""
    previous = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        assert main([]) == 0
    finally:
        os.chdir(previous)
    output = capsys.readouterr().out
    assert "ACCO " in output
    assert "Get ready:" in output
    assert "acco setup" in output
    assert "Advanced commands: acco advanced" in output


def test_setup_installs_managed_lean_skill_and_safe_profile(tmp_path: Path):
    """Claude setup should enable the safe local stack without extra commands."""
    result = setup_integrations(
        tmp_path,
        ("claude",),
        home=tmp_path / "home",
        which=lambda name: f"/usr/bin/{name}" if name == "claude" else None,
    )

    config = (tmp_path / ".acco.toml").read_text(encoding="utf-8")
    lean = tmp_path / ".claude" / "skills" / "acco-lean" / "SKILL.md"
    assert result["profile"] == "safe"
    assert result["lean_skill"] == str(lean)
    assert lean.is_file()
    assert '[profile]\nmode = "safe"' in config
    assert "history_dedup = true" in config
    assert 'model_routing = "off"' in config

    uninstall_integrations(
        tmp_path,
        ("claude",),
        home=tmp_path / "home",
        which=lambda name: f"/usr/bin/{name}" if name == "claude" else None,
    )
    assert not lean.exists()


def test_setup_cli_finishes_with_index_and_health(tmp_path: Path, capsys):
    """One setup command should configure, index, and verify the project."""
    (tmp_path / "app.py").write_text(
        "def run():\n    return 1\n",
        encoding="utf-8",
    )
    assert main(
        [
            "setup",
            str(tmp_path),
            "--host",
            "cursor",
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "safe"
    assert payload["ready"] is True
    assert payload["index"]["files"] >= 1
    assert payload["health"]["ready"] is True


def test_status_default_is_simple_but_ledger_is_preserved(tmp_path: Path, capsys):
    """The product status should replace the old view without deleting it."""
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    setup_integrations(
        tmp_path,
        ("cursor",),
        which=lambda name: f"/usr/bin/{name}" if name == "cursor" else None,
    )

    assert main(["status", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "ACCO ● ACTIVE" in output
    assert "context removed" in output
    assert "More detail:" in output

    assert main(["status", str(tmp_path), "--ledger"]) == 0
    ledger = capsys.readouterr().out
    assert "state " in ledger
    assert "remembered reads" in ledger


def test_demo_is_provider_free_and_builds_real_pack(tmp_path: Path, capsys):
    """The first-run demo should show retrieval value without calling a model."""
    (tmp_path / "auth.py").write_text(
        "def refresh_session(token):\n    return token\n",
        encoding="utf-8",
    )

    assert main(
        [
            "demo",
            str(tmp_path),
            "--query",
            "refresh session",
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_request_made"] is False
    assert payload["context_pack_tokens"] > 0
    assert "auth.py" in payload["selected_files"]


def test_start_auto_selects_single_agent_and_warms_index(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    """One detected host should make acco start need no additional selection."""
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        product.shutil,
        "which",
        lambda name: "/usr/bin/cursor" if name == "cursor" else None,
    )

    assert product.start_main(
        [str(tmp_path), "--dry-run", "--json"]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent"] == "cursor"
    assert payload["index"]["files"] >= 1


def test_start_remembers_explicit_preference(tmp_path: Path, monkeypatch):
    """A chosen start host should be reusable without changing project files."""
    monkeypatch.setenv("ACCO_STATE_DIR", str(tmp_path / "state"))
    candidates = [
        {
            "name": "claude",
            "executable": "/usr/bin/claude",
            "configured": True,
            "provider_wrapper": True,
        },
        {
            "name": "codex",
            "executable": "/usr/bin/codex",
            "configured": True,
            "provider_wrapper": True,
        },
    ]
    assert product._select_agent(tmp_path, candidates, "codex") == "codex"
    product._save_preference(tmp_path, "codex")
    assert product._select_agent(tmp_path, candidates, None) == "codex"


def test_bootstrap_persists_cli_before_running_setup(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    """uvx bootstrap should install persistently before configuring the project."""
    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        product.shutil,
        "which",
        lambda name: "/usr/bin/uv" if name == "uv" else None,
    )
    monkeypatch.setattr(
        product.subprocess,
        "run",
        lambda command, **kwargs: calls.append(list(command)) or Completed(),
    )

    import acco.command_handlers.host as host_handlers

    received: list[str] = []
    monkeypatch.setattr(
        host_handlers,
        "setup_main",
        lambda argv: received.extend(argv) or 0,
    )

    assert product.bootstrap_main([str(tmp_path), "--host", "cursor"]) == 0
    assert calls == [["uv", "tool", "install", "acco"]]
    assert received == [str(tmp_path), "--host", "cursor"]
    assert "persistent install ready via uv" in capsys.readouterr().out


def test_update_is_inspectable_and_does_not_mutate_by_default(
    monkeypatch,
    capsys,
):
    """Update should show the package-manager command unless --apply is explicit."""
    monkeypatch.setattr(
        product.shutil,
        "which",
        lambda name: "/usr/bin/uv" if name == "uv" else None,
    )
    assert product.update_main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["manager"] == "uv"
    assert payload["command"] == ["uv", "tool", "upgrade", "acco"]
    assert payload["applied"] is False


def test_frozen_update_uses_standalone_strategy(monkeypatch, capsys):
    """Frozen builds must never try to execute the ACCO binary as Python."""
    monkeypatch.setattr(product, "_is_frozen", lambda: True)
    monkeypatch.setattr(product.sys, "executable", "/opt/acco")

    assert product.update_main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["manager"] == "standalone"
    assert payload["command"] == ["/opt/acco", "update", "--apply"]
    assert "-m" not in payload["command"]


def test_frozen_homebrew_update_preserves_package_manager(monkeypatch, capsys):
    """Homebrew-managed frozen binaries should upgrade through Homebrew."""
    monkeypatch.setattr(product, "_is_frozen", lambda: True)
    monkeypatch.setattr(
        product,
        "_frozen_package_manager",
        lambda target=None: "homebrew",
    )

    assert product.update_main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["manager"] == "homebrew"
    assert payload["command"] == ["brew", "upgrade", "acco"]


def test_frozen_winget_update_preserves_package_manager(monkeypatch, capsys):
    """WinGet-managed frozen binaries should upgrade through WinGet."""
    monkeypatch.setattr(product, "_is_frozen", lambda: True)
    monkeypatch.setattr(
        product,
        "_frozen_package_manager",
        lambda target=None: "winget",
    )

    assert product.update_main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["manager"] == "winget"
    assert payload["command"][:5] == [
        "winget",
        "upgrade",
        "--id",
        "ehk2509.ACCO",
        "--exact",
    ]


def test_standalone_asset_maps_all_supported_platform_architectures():
    """Every published platform/architecture pair should resolve deterministically."""
    assert product._standalone_asset(
        system_name="Linux",
        machine="x86_64",
    ) == "acco-linux-x86_64"
    assert product._standalone_asset(
        system_name="Linux",
        machine="aarch64",
    ) == "acco-linux-arm64"
    assert product._standalone_asset(
        system_name="Darwin",
        machine="arm64",
    ) == "acco-macos-arm64"
    assert product._standalone_asset(
        system_name="Darwin",
        machine="x86_64",
    ) == "acco-macos-x86_64"
    assert product._standalone_asset(
        system_name="Windows",
        machine="AMD64",
    ) == "acco-windows-x86_64.exe"
    assert product._standalone_asset(
        system_name="Windows",
        machine="ARM64",
    ) == "acco-windows-arm64.exe"


def test_frozen_update_apply_uses_generic_verified_updater(monkeypatch, capsys):
    """Applying any frozen build update should use the standalone updater."""
    monkeypatch.setattr(product, "_is_frozen", lambda: True)
    called = []
    monkeypatch.setattr(
        product,
        "_apply_standalone_update",
        lambda: called.append(True) or "completed",
    )

    assert product.update_main(["--apply"]) == 0

    assert called == [True]
    assert "verified and installed" in capsys.readouterr().out


def test_windows_standalone_update_schedules_post_exit_replacement(
    tmp_path,
    monkeypatch,
):
    """Windows must defer replacement until the running executable exits."""
    target = tmp_path / "installed" / "acco.exe"
    target.parent.mkdir()
    target.write_bytes(b"old")
    update_dir = tmp_path / "update"
    update_dir.mkdir()
    replacement = update_dir / "acco.exe"
    replacement.write_bytes(b"new")
    popen_calls = []

    monkeypatch.setattr(product.sys, "executable", str(target))
    monkeypatch.setattr(product.platform, "system", lambda: "Windows")
    monkeypatch.setattr(product, "_standalone_asset", lambda: "acco-windows-x86_64.exe")
    monkeypatch.setattr(
        product,
        "_download_verified_standalone",
        lambda **kwargs: (update_dir, replacement),
    )
    monkeypatch.setattr(product.shutil, "which", lambda name: "pwsh" if name == "pwsh" else None)
    monkeypatch.setattr(
        product.subprocess,
        "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)),
    )

    assert product._apply_standalone_update() == "scheduled"

    assert len(popen_calls) == 1
    command, kwargs = popen_calls[0]
    assert command[:3] == ["pwsh", "-NoProfile", "-NonInteractive"]
    script = command[-1]
    assert "Wait-Process -Id" in script
    assert "Copy-Item -Force" in script
    assert str(target) in script
    assert kwargs["creationflags"] >= 0


def test_posix_standalone_update_replaces_running_binary(
    tmp_path,
    monkeypatch,
):
    """Linux/macOS should atomically replace the standalone binary in place."""
    target = tmp_path / "installed" / "acco"
    target.parent.mkdir()
    target.write_bytes(b"old")
    target.chmod(0o755)
    update_dir = tmp_path / "update"
    update_dir.mkdir()
    replacement = update_dir / "acco"
    replacement.write_bytes(b"new")
    replacement.chmod(0o755)

    monkeypatch.setattr(product.sys, "executable", str(target))
    monkeypatch.setattr(product.platform, "system", lambda: "Linux")
    monkeypatch.setattr(product, "_standalone_asset", lambda: "acco-linux-x86_64")
    monkeypatch.setattr(
        product,
        "_download_verified_standalone",
        lambda **kwargs: (update_dir, replacement),
    )

    assert product._apply_standalone_update() == "completed"
    assert target.read_bytes() == b"new"
    assert not update_dir.exists()


def test_standalone_download_rejects_bad_checksum(
    tmp_path,
    monkeypatch,
):
    """A mismatched release checksum must abort before replacement is possible."""
    update_dir = tmp_path / "update"
    update_dir.mkdir()
    monkeypatch.setattr(product.tempfile, "mkdtemp", lambda prefix: str(update_dir))

    def fake_download(url, destination):
        destination = Path(destination)
        if url.endswith(".sha256"):
            destination.write_text(
                "0" * 64 + "  acco-linux-x86_64\n",
                encoding="utf-8",
            )
        else:
            destination.write_bytes(b"tampered")

    monkeypatch.setattr(product, "urlretrieve", fake_download)

    try:
        product._download_verified_standalone(asset="acco-linux-x86_64")
    except ValueError as exc:
        assert "checksum verification failed" in str(exc)
    else:
        raise AssertionError("expected checksum rejection")

    assert not update_dir.exists()


def test_standalone_download_verifies_and_smoke_tests(
    tmp_path,
    monkeypatch,
):
    """Verified downloads should be smoke-tested before an update is accepted."""
    update_dir = tmp_path / "update"
    update_dir.mkdir()
    downloaded = b"new-verified-binary"
    digest = product.hashlib.sha256(downloaded).hexdigest()
    calls = []
    monkeypatch.setattr(product.tempfile, "mkdtemp", lambda prefix: str(update_dir))

    def fake_download(url, destination):
        calls.append(url)
        destination = Path(destination)
        if url.endswith(".sha256"):
            destination.write_text(
                f"{digest}  acco-linux-arm64\n",
                encoding="utf-8",
            )
        else:
            destination.write_bytes(downloaded)

    class Smoke:
        returncode = 0

    monkeypatch.setattr(product, "urlretrieve", fake_download)
    monkeypatch.setattr(product.subprocess, "run", lambda *args, **kwargs: Smoke())

    directory, replacement = product._download_verified_standalone(
        asset="acco-linux-arm64"
    )

    assert directory == update_dir
    assert replacement.read_bytes() == downloaded
    assert len(calls) == 2


def test_advanced_surface_keeps_power_commands_discoverable(capsys):
    """Simplifying onboarding must not hide the existing expert API."""
    assert main(["advanced"]) == 0
    output = capsys.readouterr().out
    assert "pack" in output
    assert "ranking-explain" in output
    assert "provider-proxy" in output
