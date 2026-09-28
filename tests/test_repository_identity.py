"""Regression guards for repository/account identity migration."""

from __future__ import annotations

from pathlib import Path
import subprocess


def test_old_github_identity_is_absent_from_tracked_text():
    """Tracked source/docs must not depend on the pre-migration GitHub handle."""
    root = Path(__file__).resolve().parents[1]
    old_handle = ("elyes" + "hkiri").lower()
    old_package_id = ("Elyes" + "Hkiri.ACCO").lower()

    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    tracked = [
        Path(raw.decode("utf-8"))
        for raw in completed.stdout.split(b"\0")
        if raw
    ]

    offenders: list[str] = []
    for relative in tracked:
        lowered_path = relative.as_posix().lower()
        if old_handle in lowered_path or old_package_id in lowered_path:
            offenders.append(relative.as_posix())
            continue

        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lowered = text.lower()
        if old_handle in lowered or old_package_id in lowered:
            offenders.append(relative.as_posix())

    assert offenders == []


def test_current_repository_identity_is_ehk2509():
    """Release-facing repository identity should use the current GitHub account."""
    root = Path(__file__).resolve().parents[1]

    readme = (root / "README.md").read_text(encoding="utf-8")
    marketplace = (root / ".claude-plugin" / "marketplace.json").read_text(
        encoding="utf-8"
    )
    installer = (root / "scripts" / "install-standalone.sh").read_text(
        encoding="utf-8"
    )

    expected_repo = "ehk2509/ai-coding-context-optimizer"
    assert expected_repo in readme
    assert expected_repo in marketplace
    assert expected_repo in installer

    winget_templates = sorted((root / "packaging" / "winget").glob("*.template"))
    assert len(winget_templates) == 3
    assert all(path.name.startswith("ehk2509.ACCO") for path in winget_templates)
    assert all(
        "PackageIdentifier: ehk2509.ACCO" in path.read_text(encoding="utf-8")
        for path in winget_templates
    )
