"""Release-engineering contracts for ACCO's native distributions."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_homebrew_formula_covers_all_published_unix_architectures():
    """The generated formula must have native Linux/macOS hashes for both CPUs."""
    text = (ROOT / "packaging" / "homebrew" / "acco.rb.template").read_text(
        encoding="utf-8"
    )

    assert "acco-macos-arm64" in text
    assert "acco-macos-x86_64" in text
    assert "acco-linux-arm64" in text
    assert "acco-linux-x86_64" in text
    assert "__MACOS_ARM64_SHA256__" in text
    assert "__MACOS_X86_64_SHA256__" in text
    assert "__LINUX_ARM64_SHA256__" in text
    assert "__LINUX_X86_64_SHA256__" in text


def test_winget_templates_cover_x64_and_arm64_portable_binaries():
    """WinGet metadata should expose both native Windows standalone builds."""
    installer = (
        ROOT / "packaging" / "winget" / "ehk2509.ACCO.installer.yaml.template"
    ).read_text(encoding="utf-8")
    locale = (
        ROOT / "packaging" / "winget" / "ehk2509.ACCO.locale.en-US.yaml.template"
    ).read_text(encoding="utf-8")
    version = (
        ROOT / "packaging" / "winget" / "ehk2509.ACCO.yaml.template"
    ).read_text(encoding="utf-8")

    assert "PackageIdentifier: ehk2509.ACCO" in installer
    assert "InstallerType: portable" in installer
    assert "Architecture: x64" in installer
    assert "Architecture: arm64" in installer
    assert "acco-windows-x86_64.exe" in installer
    assert "acco-windows-arm64.exe" in installer
    assert "ManifestVersion: 1.12.0" in installer
    assert "ManifestType: defaultLocale" in locale
    assert "ManifestType: version" in version


def test_installers_select_native_arm_assets():
    """Standalone install scripts must not redirect supported ARM hosts to Python."""
    shell = (ROOT / "scripts" / "install-standalone.sh").read_text(
        encoding="utf-8"
    )
    powershell = (ROOT / "scripts" / "install-standalone.ps1").read_text(
        encoding="utf-8"
    )

    assert 'arm64|aarch64) arch="arm64"' in shell
    assert 'asset="acco-$os-$arch"' in shell
    assert "standalone binary is not published yet" not in shell
    assert '"Arm64" { "arm64" }' in powershell
    assert '$asset = "acco-windows-$assetArch.exe"' in powershell


def test_standalone_workflow_builds_six_native_targets_and_supports_signing():
    """Stable native releases should cover six targets and optional OS signing."""
    workflow = (
        ROOT / ".github" / "workflows" / "standalone.yml"
    ).read_text(encoding="utf-8")

    for asset in (
        "acco-linux-x86_64",
        "acco-linux-arm64",
        "acco-macos-arm64",
        "acco-macos-x86_64",
        "acco-windows-x86_64.exe",
        "acco-windows-arm64.exe",
    ):
        assert asset in workflow

    assert "WINDOWS_SIGNING_PFX_BASE64" in workflow
    assert "APPLE_SIGNING_CERTIFICATE_P12_BASE64" in workflow
    assert "notarytool submit" in workflow
    assert "attest-build-provenance" in workflow
    assert "winget-manifests.zip" in workflow


def test_native_package_publisher_is_secret_gated():
    """External tap/WinGet publication must no-op when publisher tokens are absent."""
    workflow = (
        ROOT / ".github" / "workflows" / "publish-native-packages.yml"
    ).read_text(encoding="utf-8")

    assert "HOMEBREW_TAP_TOKEN" in workflow
    assert "WINGET_TOKEN" in workflow
    assert "gh repo create ehk2509/homebrew-acco" in workflow
    assert "$wingetCreate submit" in workflow
    assert "skipping external Homebrew tap publication" in workflow
    assert "skipping external WinGet submission" in workflow
