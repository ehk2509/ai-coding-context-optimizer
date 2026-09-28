"""Beginner-facing ACCO product UX built on the existing advanced services."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlretrieve

from .efficiency.report import dashboard_report
from .integration_setup import HOST_EXECUTABLES, detect_hosts, doctor_report
from .live_status import live_status
from .repository_service import RepositoryContextService
from .state import load as load_legacy_state
from .state import state_dir, state_path
from .wrapper import PRESETS, build_wrap_plan, run_wrap

STARTABLE_HOSTS = (
    "claude",
    "codex",
    "gemini",
    "cursor",
    "opencode",
    "openclaw",
    "hermes",
    "copilot",
    "antigravity",
)
DIRECT_EXECUTABLES = {
    **HOST_EXECUTABLES,
    "gemini": "gemini",
}


def _project_id(root: Path) -> str:
    """Return a stable opaque identifier for project-local launcher preferences."""
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]


def _preference_path(root: Path) -> Path:
    """Return the private user-state path for one project's launcher preference."""
    return state_dir() / "launcher" / f"{_project_id(root)}.json"


def _load_preference(root: Path) -> str | None:
    """Load a previously selected start host without reading project content."""
    try:
        payload = json.loads(_preference_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = payload.get("agent") if isinstance(payload, dict) else None
    return value if isinstance(value, str) and value in STARTABLE_HOSTS else None


def _save_preference(root: Path, agent: str) -> None:
    """Persist one selected launcher host in the private ACCO state directory."""
    path = _preference_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps({"agent": agent}) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _start_candidates(root: Path) -> list[dict]:
    """Return detected executable hosts with configured integrations when known."""
    known = {item.name: item for item in detect_hosts(root)}
    candidates: list[dict] = []
    for name in STARTABLE_HOSTS:
        executable_name = DIRECT_EXECUTABLES[name]
        executable = shutil.which(executable_name)
        status = known.get(name)
        if executable is None:
            continue
        candidates.append(
            {
                "name": name,
                "executable": executable,
                "configured": bool(status.configured) if status else False,
                "provider_wrapper": name in PRESETS,
            }
        )
    return candidates


def home_report(root: Path) -> dict:
    """Build a fast project-aware home-screen report without forcing indexing."""
    root = root.resolve()
    report = doctor_report(root, index=False)
    candidates = _start_candidates(root)
    preferred = _load_preference(root)
    return {
        "schema": 1,
        "root": str(root),
        "ready": report["ready"],
        "version": report["version"],
        "configured_hosts": report["configured_hosts"],
        "detected_hosts": [item["name"] for item in candidates],
        "preferred_host": preferred,
        "config_path": report["config_path"],
    }


def render_home(report: dict) -> str:
    """Render the compact beginner home screen."""
    configured = ", ".join(report["configured_hosts"]) or "none"
    detected = ", ".join(report["detected_hosts"]) or "none"
    status = "READY" if report["ready"] else "SETUP NEEDED"
    lines = [
        f"ACCO {report['version']} — {status}",
        f"project:    {report['root']}",
        f"configured: {configured}",
        f"detected:   {detected}",
        "",
    ]
    if report["ready"]:
        lines.extend(
            [
                "Start coding:",
                "  acco start",
                "",
                "Check savings/health:",
                "  acco status",
            ]
        )
    else:
        lines.extend(
            [
                "Get ready:",
                "  acco setup",
                "",
                "ACCO will detect your coding agent, install safe integrations,",
                "warm the repository index, and verify the result.",
            ]
        )
    lines.extend(["", "Advanced commands: acco advanced"])
    return "\n".join(lines)


def bootstrap_main(argv: list[str]) -> int:
    """Persistently install ACCO, then configure and verify the current project."""
    parser = argparse.ArgumentParser(prog="acco bootstrap")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--host", action="append")
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument("--no-lean", action="store_true")
    args = parser.parse_args(argv)

    if shutil.which("uv"):
        manager = "uv"
        install_command = ["uv", "tool", "install", "acco"]
    elif shutil.which("pipx"):
        manager = "pipx"
        install_command = ["pipx", "install", "--force", "acco"]
    else:
        print(
            "bootstrap requires uv or pipx for a persistent isolated install; "
            "install one of them or use 'python -m pip install --upgrade acco'",
            file=sys.stderr,
        )
        return 2

    completed = subprocess.run(
        install_command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        return int(completed.returncode)

    from .command_handlers.host import setup_main

    setup_args = [args.path]
    for host in args.host or []:
        setup_args.extend(["--host", host])
    if args.no_index:
        setup_args.append("--no-index")
    if args.no_lean:
        setup_args.append("--no-lean")

    print(f"ACCO persistent install ready via {manager}.")
    return setup_main(setup_args)


def home_main(argv: list[str]) -> int:
    """Show the project-aware ACCO home screen."""
    parser = argparse.ArgumentParser(prog="acco")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = home_report(Path(args.path))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_home(report))
    return 0


def _select_agent(
    root: Path,
    candidates: list[dict],
    requested: str | None,
) -> str:
    """Resolve explicit, remembered, single, or interactive host selection."""
    names = [item["name"] for item in candidates]
    if requested:
        if requested not in names:
            raise ValueError(
                f"agent '{requested}' is not installed; detected: "
                + (", ".join(names) or "none")
            )
        return requested

    preferred = _load_preference(root)
    if preferred in names:
        return preferred
    if len(names) == 1:
        return names[0]
    if not names:
        raise ValueError(
            "no supported coding-agent executable detected; install one, then run "
            "acco setup"
        )
    if sys.stdin.isatty():
        print("Choose coding agent:")
        for index, name in enumerate(names, start=1):
            print(f"  {index}. {name}")
        try:
            choice = input("Agent [1]: ").strip() or "1"
            selected = names[int(choice) - 1]
        except (ValueError, IndexError, EOFError) as exc:
            raise ValueError("invalid agent selection") from exc
        _save_preference(root, selected)
        return selected
    raise ValueError(
        "multiple coding agents detected; choose one with --agent "
        + "|".join(names)
    )


def start_main(argv: list[str]) -> int:
    """Warm ACCO state and launch the selected coding agent."""
    parser = argparse.ArgumentParser(prog="acco start")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--agent", choices=STARTABLE_HOSTS)
    parser.add_argument("--remember", action="store_true")
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args, trailing = parser.parse_known_args(argv)
    if trailing and trailing[0] == "--":
        trailing = trailing[1:]
    root = Path(args.path).resolve()
    try:
        candidates = _start_candidates(root)
        agent = _select_agent(root, candidates, args.agent)
        if args.remember:
            _save_preference(root, agent)
        index_status = None
        if not args.no_index:
            index_status = RepositoryContextService(root).status()

        candidate = next(item for item in candidates if item["name"] == agent)
        launch = {
            "agent": agent,
            "executable": candidate["executable"],
            "configured": candidate["configured"],
            "provider_wrapper": candidate["provider_wrapper"],
            "index": index_status,
            "argv": trailing,
        }
        if args.dry_run:
            if args.json:
                print(json.dumps(launch, indent=2))
            else:
                files = (
                    index_status.get("files")
                    if isinstance(index_status, dict)
                    else None
                )
                print(f"ACCO START — {agent}")
                if files is not None:
                    print(f"index: {files} files ready")
                print(
                    "launch: "
                    + candidate["executable"]
                    + (" " + " ".join(trailing) if trailing else "")
                )
            return 0

        if agent in PRESETS:
            plan = build_wrap_plan(
                agent,
                trailing,
                executable=candidate["executable"],
            )
            return run_wrap(root, plan)

        completed = subprocess.run(
            [candidate["executable"], *trailing],
            cwd=root,
            check=False,
        )
        return int(completed.returncode)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def product_status(root: Path, *, days: int = 7) -> dict:
    """Build the simple user-facing health and local-efficiency report."""
    root = root.resolve()
    doctor = doctor_report(root, index=True)
    efficiency = live_status(root, days=days)
    dashboard = dashboard_report(root, days=days)
    return {
        "schema": 1,
        "root": str(root),
        "version": doctor["version"],
        "ready": doctor["ready"],
        "configured_hosts": doctor["configured_hosts"],
        "index": doctor["index"],
        "health": efficiency["health"],
        "estimated_saved_tokens": efficiency["estimated_saved_tokens"],
        "waste_signals": efficiency["waste_signals"],
        "prefix_reuse_rate": efficiency["prefix_reuse_rate"],
        "working_files": efficiency["working_files"],
        "provider_calls": efficiency["provider_calls"],
        "continuity_restores": efficiency["continuity_restores"],
        "provider_usage": dashboard["provider_usage"],
        "window_days": days,
        "evidence_note": (
            "Saved tokens are local before/after context estimates, not an API "
            "invoice or universal cost-per-success claim."
        ),
    }


def status_main(argv: list[str]) -> int:
    """Show simple ACCO health, with an opt-in legacy ledger view."""
    parser = argparse.ArgumentParser(prog="acco status")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--ledger",
        action="store_true",
        help="show the historical low-level hook ledger instead",
    )
    args = parser.parse_args(argv)
    root = Path(args.path).resolve()
    if args.ledger:
        data = load_legacy_state(root)
        if args.json:
            print(
                json.dumps(
                    {
                        "state_path": str(state_path(root)),
                        "state": data,
                    },
                    indent=2,
                )
            )
        else:
            print(f"state {state_path(root)}")
            print(f"  churn_tokens {data.get('churn_tokens', 0)}")
            print(f"  churn_turns  {data.get('churn_turns', 0)}")
            print(f"  fresh_input  {data.get('fresh_input', 0)}")
            print(f"  remembered reads {len(data.get('reads') or {})}")
        return 0

    try:
        if args.days <= 0:
            raise ValueError("--days must be positive")
        report = product_status(root, days=args.days)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("ACCO ● " + ("ACTIVE" if report["ready"] else "NEEDS SETUP"))
    print(f"project: {report['root']}")
    print(
        "agents:  "
        + (", ".join(report["configured_hosts"]) or "none configured")
    )
    index = report.get("index") or {}
    print(f"index:   {index.get('files', 0)} files")
    print(f"health:  {report['health']}")
    print()
    print(f"Last {report['window_days']} day(s)")
    print(f"  context removed   ~{report['estimated_saved_tokens']:,} tokens")
    print(f"  waste signals      {report['waste_signals']}")
    reuse = report["prefix_reuse_rate"]
    print("  prefix reuse       " + ("n/a" if reuse is None else f"{reuse:.0%}"))
    print(f"  continuity restores {report['continuity_restores']}")
    print(f"  provider calls      {report['provider_calls']}")
    print()
    print("More detail: acco dashboard | acco audit | acco learn")
    print("Evidence: " + report["evidence_note"])
    return 0


def savings_main(argv: list[str]) -> int:
    """Summarize local savings evidence without converting estimates into billing."""
    parser = argparse.ArgumentParser(prog="acco savings")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.days <= 0:
            raise ValueError("--days must be positive")
        report = dashboard_report(Path(args.path), days=args.days)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {
        "schema": 1,
        "window_days": args.days,
        "estimated_tool_context_tokens": report["savings"][
            "estimated_tool_context_tokens"
        ],
        "by_feature": report["savings"]["by_feature"],
        "provider_usage": report["provider_usage"],
        "billed_usage": report["billed_usage"],
        "trust": report["savings"]["trust"],
        "task_success_verified": report["evidence"]["task_success"],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print(f"ACCO SAVINGS — {args.days} days")
    print(
        "estimated tool/context reduction: "
        f"~{payload['estimated_tool_context_tokens']:,} tokens"
    )
    for name, value in sorted(
        payload["by_feature"].items(),
        key=lambda item: -item[1],
    )[:8]:
        print(f"  {name:<28} ~{value:,}")
    print(
        "provider calls observed: "
        f"{payload['provider_usage'].get('calls', 0)}"
    )
    print("Evidence boundary: " + payload["trust"])
    return 0


def demo_main(argv: list[str]) -> int:
    """Run a provider-free repository-context demonstration."""
    parser = argparse.ArgumentParser(prog="acco demo")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--query")
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.path).resolve()
    try:
        service = RepositoryContextService(root)
        index = service.get()
        query = args.query
        if not query:
            symbol = None
            for rel, record in sorted(index.records.items()):
                if "test" in rel.lower() or "spec" in rel.lower():
                    continue
                definitions = record.definitions or []
                if definitions:
                    symbol = definitions[0].name
                    break
            query = (
                f"where is {symbol} implemented and used?"
                if symbol
                else "find the main implementation files for this repository"
            )
        pack = service.build_context(
            query,
            max_tokens=args.max_tokens,
            max_files=12,
            embeddings=False,
        )
        repository_tokens = max(
            1,
            sum(max(1, int(record.size) // 4) for record in index.records.values()),
        )
        reduction = max(
            0.0,
            1.0 - pack.estimated_tokens / repository_tokens,
        )
        payload = {
            "schema": 1,
            "query": query,
            "indexed_files": len(index.records),
            "repository_tokens_estimate": repository_tokens,
            "context_pack_tokens": pack.estimated_tokens,
            "selected_files": pack.selected_files,
            "size_reduction_fraction": reduction,
            "provider_request_made": False,
            "trust": (
                "Repository total uses a local bytes/4 planning estimate; pack "
                "tokens use ACCO's estimator. This demonstrates context size, "
                "not task success or API-cost savings."
            ),
        }
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("ACCO LOCAL DEMO")
    print(f"task: {payload['query']}")
    print(f"repository: ~{payload['repository_tokens_estimate']:,} planning tokens")
    print(f"ACCO pack:  {payload['context_pack_tokens']:,} tokens")
    print(f"size reduction: {payload['size_reduction_fraction']:.1%}")
    print(
        "selected: "
        + (", ".join(payload["selected_files"]) or "no files selected")
    )
    print("provider request: none")
    print("Evidence: " + payload["trust"])
    return 0


STANDALONE_RELEASE_BASE = (
    "https://github.com/ehk2509/ai-coding-context-optimizer/"
    "releases/latest/download"
)


def _is_frozen() -> bool:
    """Return whether ACCO is running from a frozen standalone executable."""
    return bool(getattr(sys, "frozen", False))


def _normalized_arch(machine: str | None = None) -> str:
    """Normalize common host architecture labels to ACCO release suffixes."""
    value = (machine or platform.machine()).strip().lower()
    aliases = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    try:
        return aliases[value]
    except KeyError as exc:
        raise ValueError(
            f"unsupported standalone architecture: {value or 'unknown'}"
        ) from exc


def _standalone_asset(
    *,
    system_name: str | None = None,
    machine: str | None = None,
) -> str:
    """Return the current host's standalone release asset name."""
    system = (system_name or platform.system()).strip().lower()
    arch = _normalized_arch(machine)
    if system == "windows":
        return f"acco-windows-{arch}.exe"
    if system == "darwin":
        return f"acco-macos-{arch}"
    if system == "linux":
        return f"acco-linux-{arch}"
    raise ValueError(f"unsupported standalone operating system: {system or 'unknown'}")


def _frozen_package_manager(target: Path | None = None) -> str | None:
    """Detect package-manager ownership for a frozen executable path."""
    target = (target or Path(sys.executable)).resolve()
    normalized = target.as_posix().lower()
    if "/cellar/acco/" in normalized and shutil.which("brew"):
        return "homebrew"
    if (
        "/microsoft/winget/packages/" in normalized
        or "\\microsoft\\winget\\packages\\" in str(target).lower()
    ) and shutil.which("winget"):
        return "winget"
    return None


def _upgrade_command() -> tuple[str, list[str]]:
    """Choose the least surprising available package-manager upgrade command."""
    if _is_frozen():
        frozen_manager = _frozen_package_manager()
        if frozen_manager == "homebrew":
            return "homebrew", ["brew", "upgrade", "acco"]
        if frozen_manager == "winget":
            return "winget", [
                "winget",
                "upgrade",
                "--id",
                "ehk2509.ACCO",
                "--exact",
                "--accept-source-agreements",
                "--accept-package-agreements",
                "--disable-interactivity",
            ]
        return "standalone", [sys.executable, "update", "--apply"]
    if shutil.which("uv"):
        return "uv", ["uv", "tool", "upgrade", "acco"]
    if shutil.which("pipx"):
        return "pipx", ["pipx", "upgrade", "acco"]
    return "pip", [sys.executable, "-m", "pip", "install", "--upgrade", "acco"]


def _powershell_literal(value: str) -> str:
    """Quote a PowerShell single-quoted literal."""
    return "'" + value.replace("'", "''") + "'"


def _download_verified_standalone(
    *,
    asset: str | None = None,
) -> tuple[Path, Path]:
    """Download, checksum-verify, and smoke-test the host standalone binary."""
    asset = asset or _standalone_asset()
    temporary_dir = Path(tempfile.mkdtemp(prefix="acco-update-"))
    replacement_name = "acco.exe" if asset.endswith(".exe") else "acco"
    replacement = temporary_dir / replacement_name
    checksum = temporary_dir / f"{asset}.sha256"
    try:
        urlretrieve(f"{STANDALONE_RELEASE_BASE}/{asset}", replacement)
        urlretrieve(f"{STANDALONE_RELEASE_BASE}/{asset}.sha256", checksum)
        expected = checksum.read_text(encoding="utf-8").strip().split()[0].lower()
        actual = hashlib.sha256(replacement.read_bytes()).hexdigest().lower()
        if expected != actual:
            raise ValueError("standalone ACCO update checksum verification failed")
        if not asset.endswith(".exe"):
            replacement.chmod(0o755)
        smoke = subprocess.run(
            [str(replacement), "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if smoke.returncode != 0:
            raise ValueError("downloaded standalone ACCO failed its smoke test")
        return temporary_dir, replacement
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise


def _schedule_windows_standalone_replace(
    *,
    temporary_dir: Path,
    replacement: Path,
    target: Path,
) -> None:
    """Replace a running Windows executable after the current process exits."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise ValueError("PowerShell is required to update standalone ACCO on Windows")
    script = (
        "$ErrorActionPreference='Stop';"
        f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue;"
        f"Copy-Item -Force -LiteralPath {_powershell_literal(str(replacement))} "
        f"-Destination {_powershell_literal(str(target))};"
        f"Remove-Item -Recurse -Force -LiteralPath "
        f"{_powershell_literal(str(temporary_dir))} -ErrorAction SilentlyContinue"
    )
    creationflags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
    )
    subprocess.Popen(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _apply_standalone_update() -> str:
    """Verify and install the matching standalone update for this platform."""
    asset = _standalone_asset()
    temporary_dir, replacement = _download_verified_standalone(asset=asset)
    target = Path(sys.executable).resolve()
    try:
        if platform.system().lower() == "windows":
            _schedule_windows_standalone_replace(
                temporary_dir=temporary_dir,
                replacement=replacement,
                target=target,
            )
            return "scheduled"
        mode = target.stat().st_mode
        replacement.chmod(mode)
        os.replace(replacement, target)
        shutil.rmtree(temporary_dir, ignore_errors=True)
        return "completed"
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise


def update_main(argv: list[str]) -> int:
    """Inspect or apply the recommended ACCO package upgrade command."""
    parser = argparse.ArgumentParser(prog="acco update")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    manager, command = _upgrade_command()
    payload = {
        "schema": 1,
        "manager": manager,
        "command": command,
        "applied": False,
        "returncode": None,
        "standalone_state": None,
    }
    if args.apply:
        try:
            if manager == "standalone":
                payload["standalone_state"] = _apply_standalone_update()
                returncode = 0
            else:
                completed = subprocess.run(command, check=False)
                returncode = int(completed.returncode)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        payload["applied"] = True
        payload["returncode"] = returncode
    if args.json:
        print(json.dumps(payload, indent=2))
    elif args.apply:
        if manager == "standalone" and payload["returncode"] == 0:
            if payload["standalone_state"] == "scheduled":
                print("ACCO standalone update verified and scheduled for process exit")
            else:
                print("ACCO standalone update verified and installed")
        else:
            print(
                "ACCO update "
                + ("completed" if payload["returncode"] == 0 else "failed")
            )
    else:
        print("Recommended upgrade:")
        print("  " + " ".join(command))
        print("Apply it with: acco update --apply")
    return int(payload["returncode"] or 0)


def advanced_main(argv: list[str]) -> int:
    """List the complete expert command surface separately from the home screen."""
    parser = argparse.ArgumentParser(prog="acco advanced")
    parser.parse_args(argv)
    from .cli import LEGACY_COMMANDS
    from .command_registry import DEFAULT_COMMAND_REGISTRY

    beginner = {
        "bootstrap",
        "setup",
        "start",
        "status",
        "demo",
        "savings",
        "update",
        "uninstall",
        "advanced",
    }
    commands = sorted(
        (set(DEFAULT_COMMAND_REGISTRY.names()) | set(LEGACY_COMMANDS)) - beginner
    )
    print("ACCO ADVANCED COMMANDS")
    for name in commands:
        print(f"  {name}")
    print("\nUse: acco <command> --help")
    return 0
