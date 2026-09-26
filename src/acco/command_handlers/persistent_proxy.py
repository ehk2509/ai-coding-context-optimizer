"""CLI lifecycle for persistent ACCO provider proxies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from ..integration_setup import detect_hosts
from ..persistent_proxy import (
    DURABLE_HOST_PROVIDER,
    install_persistent_profiles,
    persistent_status,
    profiles_for_root,
    run_profile,
    start_service,
    stop_service,
    uninstall_persistent_profiles,
)


def _host_args(parser: argparse.ArgumentParser) -> None:
    """Add persistent-host selection flags."""
    parser.add_argument(
        "--host",
        action="append",
        choices=[*sorted(DURABLE_HOST_PROVIDER), "all"],
        help=(
            "host to attach persistently; repeat for multiple hosts. "
            "Without this flag ACCO auto-detects Claude/Codex."
        ),
    )


def _mapping(values: list[str] | None, *, value_type: type = str) -> dict:
    """Parse repeatable KEY=VALUE flags into a deterministic mapping."""
    result = {}
    for raw in values or []:
        if "=" not in raw:
            raise ValueError(f"expected PROVIDER=VALUE, got: {raw}")
        key, value = raw.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key not in {"anthropic", "openai", "gemini"}:
            raise ValueError(f"unsupported provider mapping: {key}")
        if not value:
            raise ValueError(f"empty value for provider: {key}")
        result[key] = value_type(value)
    return result


def _selected_hosts(root: Path, requested: list[str] | None) -> tuple[str, ...]:
    """Resolve explicit or auto-detected durable host targets."""
    if requested:
        if "all" in requested:
            return tuple(sorted(DURABLE_HOST_PROVIDER))
        return tuple(dict.fromkeys(requested))
    statuses = detect_hosts(root)
    detected = [
        item.name
        for item in statuses
        if item.detected and item.name in DURABLE_HOST_PROVIDER
    ]
    if not detected:
        raise ValueError(
            "no persistently attachable host detected; use --host claude "
            "or --host codex explicitly"
        )
    return tuple(detected)


def proxy_main(argv: list[str]) -> int:
    """Manage persistent background provider proxies and durable host routing."""
    parser = argparse.ArgumentParser(prog="acco proxy")
    sub = parser.add_subparsers(dest="action", required=True)

    install = sub.add_parser(
        "install",
        help="install user-session autostart and attach supported hosts",
    )
    install.add_argument("path", nargs="?", default=".")
    _host_args(install)
    install.add_argument(
        "--upstream",
        action="append",
        metavar="PROVIDER=URL",
        help="provider upstream override; repeatable and never stores credentials",
    )
    install.add_argument(
        "--port",
        action="append",
        metavar="PROVIDER=PORT",
        help="stable provider listener port override; repeatable",
    )
    install.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="show installed profiles and listener state")
    status.add_argument("path", nargs="?", default=".")
    status.add_argument("--json", action="store_true")

    start = sub.add_parser("start", help="start installed project proxy services")
    start.add_argument("path", nargs="?", default=".")

    stop = sub.add_parser("stop", help="stop installed project proxy services")
    stop.add_argument("path", nargs="?", default=".")

    uninstall = sub.add_parser(
        "uninstall",
        help="detach hosts and remove project proxy autostart services",
    )
    uninstall.add_argument("path", nargs="?", default=".")
    uninstall.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    root = Path(args.path).resolve()

    try:
        if args.action == "install":
            hosts = _selected_hosts(root, args.host)
            result = install_persistent_profiles(
                root,
                hosts,
                upstreams=_mapping(args.upstream),
                ports=_mapping(args.port, value_type=int),
            )
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print("ACCO PERSISTENT PROXY — INSTALLED")
                print(f"project: {result['root']}")
                print("hosts:   " + ", ".join(result["hosts"]))
                for profile in result["profiles"]:
                    print(
                        f"{profile['provider']:<10} "
                        f"{profile['local_base_url']} "
                        f"[{profile['service_kind']}]"
                    )
                print("status:  acco proxy status " + result["root"])
            return 0

        if args.action == "status":
            result = persistent_status(root)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                state = "INSTALLED" if result["installed"] else "NOT INSTALLED"
                print(f"ACCO PERSISTENT PROXY — {state}")
                print(f"project: {result['root']}")
                for profile in result["profiles"]:
                    runtime = "running" if profile["running"] else "stopped"
                    print(
                        f"{profile['provider']:<10} {runtime:<8} "
                        f"{profile['local_base_url']} "
                        f"hosts={','.join(profile['hosts'])}"
                    )
            return 0

        if args.action == "start":
            profiles = profiles_for_root(root)
            if not profiles:
                raise ValueError("no persistent proxy profiles installed for this project")
            for profile in profiles:
                start_service(profile)
            print(f"started {len(profiles)} persistent proxy profile(s)")
            return 0

        if args.action == "stop":
            profiles = profiles_for_root(root)
            if not profiles:
                raise ValueError("no persistent proxy profiles installed for this project")
            for profile in profiles:
                stop_service(profile)
            print(f"stopped {len(profiles)} persistent proxy profile(s)")
            return 0

        result = uninstall_persistent_profiles(root)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("ACCO PERSISTENT PROXY — UNINSTALLED")
            print(f"project: {result['root']}")
            print(f"profiles removed: {len(result['removed_profiles'])}")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        print(str(detail).strip(), file=sys.stderr)
        return 2


def proxy_run_main(argv: list[str]) -> int:
    """Run one stored persistent profile for an OS-native user supervisor."""
    parser = argparse.ArgumentParser(prog="acco proxy-run")
    parser.add_argument("profile_id")
    args = parser.parse_args(argv)
    try:
        return run_profile(args.profile_id)
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
