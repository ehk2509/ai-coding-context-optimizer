"""CLI handlers for ACCO's everyday-efficiency product surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ..context_audit import context_audit_report
from ..efficiency.guardian import guardian_report
from ..lean_skill import SKILL_TEXT, install_lean_skill
from ..live_status import live_status, render_status
from ..wrapper import build_wrap_plan, run_wrap


def guardian_main(argv: list[str]) -> int:
    """Inspect the latest pre-compaction guardian checkpoint."""
    parser = argparse.ArgumentParser(prog="acco guardian")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = guardian_report(Path(args.path))
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print("ACCO COMPACTION GUARDIAN")
    if not result["available"]:
        print("checkpoint: none")
        return 0
    checkpoint = result["checkpoint"]
    print(f"source: {checkpoint.get('source')}")
    print(f"task:   {checkpoint.get('task')}")
    print(f"files:  {len(checkpoint.get('working_files', []))}")
    print(f"tests:  {len(checkpoint.get('validations', []))}")
    return 0


def wrap_main(argv: list[str]) -> int:
    """Launch one coding agent through an ephemeral ACCO provider proxy."""
    parser = argparse.ArgumentParser(
        prog="acco wrap",
        description=(
            "Launch a coding CLI through ACCO. Claude/Codex/Gemini are detected "
            "by executable; other commands are inferred from --model or provider env."
        ),
        epilog=(
            "examples: acco wrap claude | acco wrap aider -- --model gpt-4.1 | "
            "acco wrap opencode | acco wrap --provider anthropic my-agent"
        ),
    )
    parser.add_argument("agent", metavar="COMMAND")
    parser.add_argument("--path", default=".")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--provider")
    parser.add_argument("--upstream")
    parser.add_argument("--base-url-env")
    parser.add_argument("--executable")
    parser.add_argument(
        "--proxy-url",
        help=(
            "reuse an already-running ACCO-compatible proxy instead of starting "
            "an ephemeral provider proxy"
        ),
    )
    parser.add_argument(
        "--model-routing",
        choices=("off", "observe", "calibrated"),
        default="off",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    if "--" in argv:
        separator = argv.index("--")
        wrapper_argv = argv[:separator]
        trailing = argv[separator + 1 :]
    else:
        wrapper_argv = argv
        trailing = []
    args = parser.parse_args(wrapper_argv)
    try:
        plan = build_wrap_plan(
            args.agent,
            trailing,
            bind=args.bind,
            port=args.port,
            provider=args.provider,
            upstream=args.upstream,
            base_url_env=args.base_url_env,
            executable=args.executable,
        )
        if args.dry_run:
            payload = plan.to_dict()
            payload["model_routing"] = args.model_routing
            payload["proxy_url"] = args.proxy_url
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(
                    f"{plan.base_url_env}={plan.local_base_url} "
                    f"{plan.executable} {' '.join(plan.argv)}"
                )
            return 0
        return run_wrap(
            Path(args.path),
            plan,
            model_routing=args.model_routing,
            proxy_url=args.proxy_url,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _preset_alias(agent: str, argv: list[str]) -> int:
    """Dispatch a short agent alias through the common wrapper handler."""
    return wrap_main([agent, "--", *argv])


def claude_main(argv: list[str]) -> int:
    """Launch Claude Code through the ACCO provider wrapper."""
    return _preset_alias("claude", argv)


def codex_main(argv: list[str]) -> int:
    """Launch Codex through the ACCO provider wrapper."""
    return _preset_alias("codex", argv)


def gemini_main(argv: list[str]) -> int:
    """Launch Gemini CLI through the ACCO provider wrapper."""
    return _preset_alias("gemini", argv)


def lean_skill_main(argv: list[str]) -> int:
    """Print or install ACCO's portable terse-output skill."""
    parser = argparse.ArgumentParser(prog="acco lean-skill")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument(
        "--host",
        choices=("claude", "agents", "all"),
        default="claude",
    )
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.install:
        sys.stdout.write(SKILL_TEXT)
        return 0
    try:
        paths = install_lean_skill(
            Path(args.path),
            host=args.host,
            force=args.force,
        )
    except (OSError, ValueError, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {"installed": [str(path) for path in paths]}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for path in paths:
            print(path)
    return 0


def context_audit_main(argv: list[str]) -> int:
    """Audit cross-host always-on and on-demand context configuration."""
    parser = argparse.ArgumentParser(prog="acco context-audit")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--project-only", action="store_true")
    parser.add_argument("--probe-mcp", action="store_true")
    parser.add_argument("--mcp-timeout", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = context_audit_report(
            Path(args.path),
            user_scope=not args.project_only,
            probe_mcp=args.probe_mcp,
            mcp_timeout=args.mcp_timeout,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print("ACCO CONTEXT AUDIT")
    print(f"always-on: {report['always_on_tokens']:,} tokens")
    print(f"items:     {len(report['items'])}")
    print(f"oversized: {len(report['oversized'])}")
    print(f"duplicates:{len(report['duplicates'])}")
    for item in report["recommendations"]:
        print(
            f"[{item['priority']}] {item['action']} — {item['evidence']}"
        )
    return 0


def statusline_main(argv: list[str]) -> int:
    """Render one compact local efficiency status line."""
    parser = argparse.ArgumentParser(prog="acco statusline")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = live_status(Path(args.path), days=args.days)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_status(result))
    return 0
