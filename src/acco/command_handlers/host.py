"""Host integration CLI handlers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..claude_plugin import plugin_status, render_plugin
from ..client_capabilities import capability_report
from ..fastpath import status as fastpath_status
from ..host_transport import transport_report
from ..host_validate import validate_host
from ..integration_setup import (
    HOSTS,
    doctor_report,
    setup_integrations,
    uninstall_integrations,
)
from ..serve import serve


def claude_plugin_path_main(argv: list[str]) -> int:
    """Render the Claude Code plugin and print its absolute directory."""
    parser = argparse.ArgumentParser(prog="acco claude-plugin-path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = render_plugin()
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result = plugin_status()
    result["path"] = str(path)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(path)
    return 0


def fastpath_status_main(argv: list[str]) -> int:
    """Report optional Rust accelerator availability and active capabilities."""
    parser = argparse.ArgumentParser(prog="acco fastpath-status")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = fastpath_status()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("ACCO FASTPATH")
        print(f"backend: {result['backend']}")
        capabilities = result["capabilities"]
        print("capabilities: " + (", ".join(capabilities) if capabilities else "none"))
        if not result["available"]:
            print("fallback: Python reference implementation")
    return 0



def client_capabilities_main(argv: list[str]) -> int:
    """Report conservative host capability guarantees and feature prerequisites."""
    parser = argparse.ArgumentParser(prog="acco client-capabilities")
    parser.add_argument("--client", help="claude-code, codex, cursor, opencode, openclaw, hermes, copilot, antigravity, gemini-cli, or generic-mcp")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = capability_report(args.client)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    if args.client:
        record = report["client"]
        print(f"ACCO CLIENT CAPABILITIES — {record['client']}")
        for name, level in record["capabilities"].items():
            print(f"  {name:<24} {level}")
        if record["note"]:
            print("note: " + record["note"])
        print("feature prerequisites:")
        for name, evidence in report["features"].items():
            state = "guaranteed" if evidence["guaranteed"] else (
                "fallback" if evidence["available_with_fallback"] else "unavailable"
            )
            print(f"  {name:<26} {state}")
        return 0

    print("ACCO CLIENT CAPABILITY REGISTRY")
    for name, record in report["clients"].items():
        guaranteed = sum(
            1 for level in record["capabilities"].values() if level == "yes"
        )
        conditional = sum(
            1 for level in record["capabilities"].values()
            if level in {"conditional", "advisory"}
        )
        print(f"  {name:<14} guaranteed={guaranteed} conditional={conditional}")
    print("Use --client NAME for feature-level prerequisites.")
    return 0


def transport_status_main(argv: list[str]) -> int:
    """Report provider-transport support without overstating host guarantees."""
    parser = argparse.ArgumentParser(prog="acco transport-status")
    parser.add_argument("--host")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = transport_report(args.host)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    if args.host:
        record = report["host"]
        print(f"ACCO TRANSPORT — {record['host']}")
        print(f"foreground: {record['foreground']}")
        print(f"persistent: {record['persistent']}")
        print(f"provider:   {record['provider'] or 'dynamic'}")
        if record["note"]:
            print("note: " + record["note"])
        return 0
    print("ACCO HOST TRANSPORT REGISTRY")
    for name, record in report["hosts"].items():
        print(
            f"  {name:<9} foreground={record['foreground']:<14} "
            f"persistent={record['persistent']}"
        )
    return 0


def host_check_main(argv: list[str]) -> int:
    """Run the host check command."""
    parser = argparse.ArgumentParser(prog="acco host-check")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--host", default="claude", help="host executable to inspect")
    parser.add_argument(
        "--live-evidence",
        help="host debug transcript proving updatedToolOutput acceptance",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return nonzero unless hooks are configured and transport recovery passes",
    )
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="return nonzero unless supplied host debug evidence verifies replacement acceptance",
    )
    args = parser.parse_args(argv)
    try:
        result = validate_host(
            Path(args.path),
            executable=args.host,
            live_evidence=Path(args.live_evidence) if args.live_evidence else None,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    if args.require_live and not result["live_verified"]:
        return 1
    if args.require_ready and not result["ready"]:
        return 1
    return 0


def serve_main(argv: list[str]) -> int:
    """Run the serve command."""
    parser = argparse.ArgumentParser(prog="acco serve")
    parser.add_argument("path", nargs="?", default=".")
    args = parser.parse_args(argv)
    return serve(Path(args.path).resolve())


def _hosts_argument(parser: argparse.ArgumentParser) -> None:
    """Add repeatable host selection to an integration command."""
    parser.add_argument(
        "--host",
        action="append",
        choices=[*HOSTS, "all"],
        help="host to configure; repeat for multiple hosts (default: auto-detect)",
    )


def setup_main(argv: list[str]) -> int:
    """Auto-detect and configure ACCO integrations."""
    parser = argparse.ArgumentParser(prog="acco setup")
    parser.add_argument("path", nargs="?", default=".")
    _hosts_argument(parser)
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="skip the initial structural index warm-up",
    )
    parser.add_argument(
        "--no-lean",
        action="store_true",
        help="do not install ACCO's managed Lean skill for Claude",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return nonzero unless setup finishes in a ready state",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = Path(args.path)
        result = setup_integrations(
            root,
            tuple(args.host) if args.host else None,
            install_lean=not args.no_lean,
        )
        health = doctor_report(root, index=not args.no_index)
        result["ready"] = health["ready"]
        result["health"] = health
        result["index"] = health["index"]
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
        return 1 if args.require_ready and not result["ready"] else 0
    print("ACCO SETUP — " + ("READY" if result["ready"] else "NEEDS ATTENTION"))
    print(f"project: {result['root']}")
    print(f"profile: {result.get('profile', 'safe')}")
    print(f"config:  {result['config']}")
    if result["configured_hosts"]:
        print("configured: " + ", ".join(result["configured_hosts"]))
    else:
        print("configured: none (no supported host detected)")
        print("hint: rerun with --host " + "|".join([*HOSTS, "all"]))
    if result.get("lean_skill"):
        print("lean:    enabled")
    index = result.get("index") or {}
    if index:
        print(f"index:   {index.get('files', 0)} files ready")
    if result["ready"]:
        print("start:   acco start")
    else:
        print("repair:  acco doctor " + result["root"])
    return 1 if args.require_ready and not result["ready"] else 0


def doctor_main(argv: list[str]) -> int:
    """Run one consolidated installation and integration health check."""
    parser = argparse.ArgumentParser(prog="acco doctor")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = doctor_report(Path(args.path), index=not args.no_index)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"ACCO DOCTOR {report['version']}")
        print("status: " + ("READY" if report["ready"] else "NEEDS ATTENTION"))
        print(f"cli:    {report['acco_executable'] or 'not found in PATH'}")
        print(f"config: {report['config_path'] or 'not found'}")
        if report["config_error"]:
            print(f"config error: {report['config_error']}")
        for host in report["hosts"]:
            detected = "detected" if host["detected"] else "not detected"
            configured = "configured" if host["configured"] else "not configured"
            print(f"{host['name']:<7} {detected}, {configured}")
        if report["index"]:
            print(
                "index:  "
                f"{report['index']['files']} files, "
                f"version {report['index']['index_version']}"
            )
        elif report["index_error"]:
            print(f"index error: {report['index_error']}")
        print(f"claude usage evidence: {report['claude_transcripts']} transcript(s)")
        if not report["ready"]:
            print("repair: acco setup " + report["root"])
    return 1 if args.require_ready and not report["ready"] else 0


def uninstall_main(argv: list[str]) -> int:
    """Safely remove ACCO-owned host integration entries."""
    parser = argparse.ArgumentParser(prog="acco uninstall")
    parser.add_argument("path", nargs="?", default=".")
    _hosts_argument(parser)
    parser.add_argument("--remove-config", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = uninstall_integrations(
            Path(args.path),
            tuple(args.host) if args.host else None,
            remove_config=args.remove_config,
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("ACCO UNINSTALL")
        print("removed: " + ", ".join(result["removed_hosts"]))
        if result["config_removed"]:
            print("project config removed")
    return 0


def completion_main(argv: list[str]) -> int:
    """Generate lightweight shell completion for top-level commands."""
    parser = argparse.ArgumentParser(prog="acco completion")
    parser.add_argument("shell", choices=["bash", "zsh", "fish", "powershell"])
    args = parser.parse_args(argv)

    from ..command_registry import DEFAULT_COMMAND_REGISTRY

    names = " ".join(DEFAULT_COMMAND_REGISTRY.names())
    if args.shell == "bash":
        print(
            "_acco_complete() {\n"
            '  local cur="${COMP_WORDS[COMP_CWORD]}"\n'
            f'  COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
            "}\n"
            "complete -F _acco_complete acco"
        )
    elif args.shell == "zsh":
        print(f"#compdef acco\n_arguments \'1:command:({names})\'")
    elif args.shell == "fish":
        for name in DEFAULT_COMMAND_REGISTRY.names():
            print(f"complete -c acco -n \'__fish_use_subcommand\' -a \'{name}\'")
    else:
        quoted = ", ".join(
            repr(name)
            for name in DEFAULT_COMMAND_REGISTRY.names()
        )
        print(
            "Register-ArgumentCompleter -Native -CommandName acco -ScriptBlock {\n"
            "  param($wordToComplete, $commandAst, $cursorPosition)\n"
            f"  $commands = @({quoted})\n"
            "  $commands | Where-Object { $_ -like \"$wordToComplete*\" } | "
            "ForEach-Object {\n"
            "    [System.Management.Automation.CompletionResult]::new("
            "$_, $_, 'ParameterValue', $_)\n"
            "  }\n"
            "}"
        )
    return 0


def commands_main(argv: list[str]) -> int:
    """List discoverable top-level commands."""
    parser = argparse.ArgumentParser(prog="acco commands")
    parser.parse_args(argv)
    from ..command_registry import DEFAULT_COMMAND_REGISTRY

    print("ACCO COMMANDS")
    for name in DEFAULT_COMMAND_REGISTRY.names():
        print(name)
    print("\nUse: acco <command> --help")
    return 0
