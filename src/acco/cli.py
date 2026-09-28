"""CLI: sessions | outline | audit | map | estimate | filter | budget."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit
from .sessions import analyze, transcript_paths
from .estimate import DEFAULT_MODEL, Counter, estimate_tokens, format_tokens
from .filter_output import filter_command_output
from .hook import main as hook_main
from .install import install
from .mapstat import map_freshness
from .mcp import probe_all
from .policy import advise, snapshot
from .prune import classify_servers, disable_unused
from .skeleton import build_map, skeletonize
from .snippet import extract_from_path
from .state import load as load_state
from .state import state_path

LEGACY_COMMANDS = (
    "audit",
    "benchmark",
    "budget",
    "check",
    "estimate",
    "filter",
    "hook",
    "install",
    "map",
    "mcp-prune",
    "outline",
    "output",
    "outputs-prune",
    "policy",
    "sessions",
    "snippet",
    "status",
)

# share of a context window that always-on content should not exceed
ALWAYS_ON_WARN = 0.02
ALWAYS_ON_FAIL = 0.05


def _counter(args: argparse.Namespace) -> Counter:
    """Handle counter."""
    return Counter(exact=getattr(args, "exact", False),
                   model=getattr(args, "model", DEFAULT_MODEL))


def cmd_map(args: argparse.Namespace) -> int:
    """Handle cmd map."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"not found: {root}", file=sys.stderr)
        return 1
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    target = Path(args.out) if getattr(args, "out", None) else root / "CODEMAP.md"
    if getattr(args, "refresh_if_stale", False) and not getattr(args, "out", None):
        args.out = str(target)
    if getattr(args, "check_stale", False) and not getattr(args, "refresh_if_stale", False):
        fresh, reason = map_freshness(root, target if target.exists() else None)
        print(reason)
        return 0 if fresh else 2
    if getattr(args, "refresh_if_stale", False):
        fresh, reason = map_freshness(root, target if target.is_file() else None)
        if fresh and target.is_file():
            print(reason)
            return 0
    text = build_map(root, docstrings=args.docstrings, max_tokens=args.max_tokens,
                     use_gitignore=not args.no_gitignore)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({format_tokens(estimate_tokens(text))} tokens)")
    else:
        sys.stdout.write(text)
    return 0


def cmd_estimate(args: argparse.Namespace) -> int:
    """Handle cmd estimate."""
    counter = _counter(args)
    if args.file:
        path = Path(args.file)
        if not path.is_file():
            print(f"not found: {args.file}", file=sys.stderr)
            return 1
        text = path.read_text(encoding="utf-8", errors="replace")
        suffix = path.suffix
    else:
        text, suffix = sys.stdin.read(), ""
    try:
        n = counter.count(text, suffix)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{n} tokens ({counter.label}, ≈{format_tokens(n)}) chars={len(text)}")
    return 0


def cmd_filter(args: argparse.Namespace) -> int:
    """Handle cmd filter."""
    text = sys.stdin.read()
    command = getattr(args, "command", "") or ""
    filtered = filter_command_output(text, command=command,
                                     max_lines=max(1, args.max_lines),
                                     keep_tail=max(0, args.keep_tail))
    if filtered != text:
        from .output_store import store_output
        note = "\n[acco: original saved; acco output {id} --offset 1 --limit 80]\n"
        candidate = filtered + note.format(id="0" * 32)
        if estimate_tokens(text) - estimate_tokens(candidate) >= 50 and len(candidate.encode()) < len(text.encode()):
            try:
                output_id = store_output({"stdout": text, "stderr": "", "interrupted": False, "isImage": False})
                filtered += note.format(id=output_id)
            except OSError:
                filtered = text
        else:
            filtered = text
    sys.stdout.write(filtered)
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    """Handle cmd install."""
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    path = install(root, user=getattr(args, "user", False),
                   templates=getattr(args, "templates", False))
    print(f"wrote {path}")
    print("  PreToolUse  Read          → deny full reads of large source files")
    print("  PostToolUse Bash|Read → recoverable log filtering + remember full reads")
    print("  SessionStart / UserPromptSubmit → session state reset + conditional /clear suggestion")
    if getattr(args, "templates", False):
        print("  .claude/skills/token-budget/SKILL.md (on-demand)")
    print("Disable the read guard with ACCO_GUARD=0")
    return 0


def cmd_snippet(args: argparse.Namespace) -> int:
    """Handle cmd snippet."""
    path = Path(args.file)
    if not path.is_file():
        print(f"not found: {args.file}", file=sys.stderr)
        return 1
    try:
        hit = extract_from_path(path, args.symbol)
    except (ValueError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if hit is None:
        print(f"symbol not found: {args.symbol} in {path}", file=sys.stderr)
        return 1
    text, start, end = hit
    sys.stdout.write(text)
    if not args.quiet:
        print(f"# {path.name}:{start}-{end}  {args.symbol}", file=sys.stderr)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Handle cmd audit."""
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    try:
        report = audit(root, _counter(args), window=args.window,
                       user_scope=not args.no_user_scope)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    always = [i for i in report.items if i.always_on and i.tokens]
    demand = [i for i in report.items if not i.always_on and i.tokens]
    mcp_total = 0

    print(f"ALWAYS-ON CONTEXT ({report.counter_label}, window={report.window})")
    print("  paid on every single turn of every session\n")
    if not always:
        print("  (nothing found — no CLAUDE.md, rules, or memory index)")
    for item in sorted(always, key=lambda i: -i.tokens):
        note = f"  — {item.note}" if item.note else ""
        print(f"  {item.tokens:7}  {item.kind:9} {item.path}{note}")

    total = report.always_on
    share = total / report.window if report.window else 0
    print(f"\n  {total:7}  TOTAL always-on  ({share:.1%} of the window)")

    if demand:
        print("\nON DEMAND (costs nothing until it is needed)")
        for item in sorted(demand, key=lambda i: -i.tokens):
            note = f"  — {item.note}" if item.note else ""
            print(f"  {item.tokens:7}  {item.kind:9} {item.path}{note}")

    if report.mcp_servers:
        print(f"\nMCP SERVERS ({len(report.mcp_servers)}) — tool schemas ride along "
              "with every request")
        if args.probe_mcp:
            costs = probe_all(root, timeout=args.mcp_timeout)
            measured = mcp_total = sum(c.tokens or 0 for c in costs)
            for cost in costs:
                if cost.measured:
                    print(f"  {cost.tokens:7}  {cost.name:18} {cost.tools} tools")
                else:
                    print(f"  {'—':>7}  {cost.name:18} {cost.status}")
            if measured:
                print(f"  {measured:7}  measured total "
                      f"({measured / report.window:.1%} of the window)")
                total += measured
                share = total / report.window if report.window else 0
        else:
            for name in report.mcp_servers:
                print(f"           {name}")
            print("  --probe-mcp measures their schemas (launches each server)")

    print("\nVERDICT")
    if report.mcp_servers and args.probe_mcp:
        print(f"  always-on including MCP schemas: {total:,} tokens")
    if share >= ALWAYS_ON_FAIL:
        print(f"  ✗ always-on is {share:.1%} of the window — over the {ALWAYS_ON_FAIL:.0%} "
              "ceiling")
    elif share >= ALWAYS_ON_WARN:
        print(f"  ! always-on is {share:.1%} of the window — past the "
              f"{ALWAYS_ON_WARN:.0%} comfort line")
    else:
        print(f"  ✓ always-on is {share:.1%} of the window")

    hints = []
    for item in always:
        if item.kind == "claude_md" and "over the" in item.note:
            hints.append(f"trim {item.path} ({item.note}) or split it into "
                         ".claude/rules/ with paths: frontmatter")
        if item.kind == "rule" and "no paths:" in item.note:
            hints.append(f"add paths: frontmatter to {item.path} so it loads only "
                         "when relevant files are touched")
    if report.mcp_servers:
        if args.probe_mcp and mcp_total:
            hints.append(
                f"MCP schemas cost {mcp_total:,} tokens on every request — disable "
                "any server you do not actually call"
            )
        else:
            hints.append("re-run with --probe-mcp to measure what your MCP servers "
                         "cost per request")
    if hints:
        print("\nTRIMS")
        for hint in dict.fromkeys(hints):
            print(f"  - {hint}")
    return 0


def cmd_outline(args: argparse.Namespace) -> int:
    """Signatures of one file instead of the whole thing.

    File reads are the largest single source of context tokens in a real
    session, and most of a read is body the model does not need to navigate.
    """
    path = Path(args.file)
    if not path.is_file():
        print(f"not found: {args.file}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8", errors="replace")
    outlined = skeletonize(
        text,
        path.suffix,
        docstrings=args.docstrings,
        line_numbers=not args.no_line_numbers,
    )
    before = estimate_tokens(text, path.suffix)
    after = estimate_tokens(outlined, path.suffix)
    sys.stdout.write(outlined)
    if not args.quiet:
        cut = 100 * (1 - after / before) if before else 0
        print(
            f"\n# {path.name}: {before} → {after} tokens ({cut:.0f}% smaller). "
            f"Read a line range (the left gutter) to see any body.",
            file=sys.stderr,
        )
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    """Report where tokens actually went, from Claude Code's own transcripts."""
    root = Path(args.path).resolve()
    paths = transcript_paths(root, all_projects=args.all_projects)
    if not paths:
        where = "any project" if args.all_projects else str(root)
        print(f"no session transcripts found for {where}", file=sys.stderr)
        print("(Claude Code writes them under ~/.claude/projects/)", file=sys.stderr)
        return 1

    report = analyze(paths)
    print(f"SESSIONS ANALYSED: {report.sessions}\n")

    fresh = report.fresh_input
    print("RECORDED API USAGE (token counts, not dollar cost)")
    print(f"  {'fresh (uncached)':26} {fresh:>12,}")
    print(f"  {'cache reads':26} "
          f"{report.usage['cache_read_input_tokens']:>12,}")
    print(f"  {'output':26} {report.usage['output_tokens']:>12,}")
    print(f"  {'cache hit rate':26} {report.cache_hit_rate:>11.1%}")
    print(f"  counted over {len(report.turns):,} API responses "
          "(deduped by message id)")

    def share_of_fresh(n: int) -> str:
        """Every saving is quoted against the real bill, never against itself."""
        return f"{100 * n / fresh:.1f}% of fresh input" if fresh else "n/a"

    churn, churn_turns, worst = report.cache_churn()
    print("\nCACHE WRITE CLASSIFICATION (heuristic, not avoidable waste)")
    from collections import Counter as UsageCounter
    for kind, count in UsageCounter(t.cache_kind for t in report.turns).items():
        print(f"  {kind}: {count} responses")
    if churn:
        print(f"  suspected recreated overlap: {churn:,} tokens across {churn_turns} responses")
        print("  Initial observations excluded. Prefix changes and expiry cannot be distinguished from usage alone.")
        print("  Consider /clear only between unrelated tasks; ongoing work may need its history.")
    if getattr(args, "rates", None):
        from .pricing import load_rates, cost
        try:
            print("\nCOST AT SUPPLIED RATES " + json.dumps(cost(report, load_rates(args.rates))))
        except (OSError, ValueError) as exc:
            print(f"pricing error: {exc}", file=sys.stderr)
            return 2
    rows = report.by_tool()
    total = sum(r[1] for r in rows)
    print(f"\nESTIMATED TOOL RESULT SIZE (one copy; not billed attribution) — {total:,} tokens "
          f"({share_of_fresh(total)})")
    for name, tokens, calls in rows[: args.top]:
        share = 100 * tokens / total if total else 0
        print(f"  {name:18} {tokens:>11,}  {share:5.1f}%  {calls:>5} calls  "
              f"avg {tokens // max(calls, 1):>6}")

    print("\nLARGEST SINGLE RESULTS")
    for call in report.biggest(args.top):
        print(f"  {call.tokens:>9,}  {call.name:14} {call.label[-56:]}")

    img_tokens, img_count = report.image_cost()
    if img_count:
        share = 100 * img_tokens / total if total else 0
        print(f"\nIMAGE PAYLOADS — ~{img_tokens:,} estimated tokens, {img_count} images, "
              f"{share:.1f}% of tool output")
        unknown = sum(c.unknown_size for c in report.calls if c.kind == "image")
        print(f"  approximate dimension-based estimate, not model-specific billing; {unknown} unknown sizes excluded")

    dupes = report.duplicate_reads()
    if dupes:
        wasted = sum(row[2] for row in dupes)
        print(f"\nREPEATED READS — ~{wasted:,} tokens within the same session/context epoch; necessity unknown")
        for path, times, cost in dupes[: args.top]:
            print(f"  {cost:>9,}  read {times}× identically  {path[-56:]}")

    before, after, files = report.outline_savings()
    if before:
        cut = 100 * (1 - after / before)
        print("\nHYPOTHETICAL ONE-SHOT OUTLINE REDUCTION (excludes follow-up reads)")
        print(f"  {before:,} → {after:,} tokens ({cut:.0f}% smaller)")
        print(f"  estimated size reduction {before - after:,} = "
              f"{share_of_fresh(before - after)}")
        for path, was, now in files[: args.top]:
            print(f"  {was:>8,} → {now:>7,}  {path[-56:]}")
        print("\n  acco outline <file>   # signatures only, then read ranges")

    print("\nPOLICY")
    for item in advise(report):
        stake = f"  (~{item.tokens_at_stake:,} tokens)" if item.tokens_at_stake else ""
        print(f"  [{item.kind}] {item.detail}{stake}")
    print("  Result-size ratios are not bill shares or savings ceilings.")
    print(f"\n  snapshot {snapshot(report, root)}")
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    """Handle cmd policy."""
    root = Path(args.path).resolve()
    paths = transcript_paths(root, all_projects=args.all_projects)
    if not paths:
        print("no session transcripts found", file=sys.stderr)
        return 1
    report = analyze(paths, keep_content=False)
    for item in advise(report):
        stake = f" (~{item.tokens_at_stake:,})" if item.tokens_at_stake else ""
        print(f"{item.kind}: {item.detail}{stake}")
    print(f"snapshot {snapshot(report, root)}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Handle cmd check."""
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    rc = 0
    try:
        report = audit(root, _counter(args), window=args.window,
                       user_scope=not args.no_user_scope)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    share = report.always_on / report.window if report.window else 0
    if share >= ALWAYS_ON_FAIL:
        print(f"FAIL always-on {report.always_on} tokens ({share:.1%} of window)")
        rc = 1
    elif share >= ALWAYS_ON_WARN:
        print(f"WARN always-on {report.always_on} tokens ({share:.1%} of window)")
    else:
        print(f"OK always-on {report.always_on} tokens ({share:.1%} of window)")
    fresh, reason = map_freshness(root)
    print(reason)
    if not fresh and args.fail_stale_map:
        rc = 1
    return rc


def cmd_status(args: argparse.Namespace) -> int:
    """Handle cmd status."""
    root = Path(args.path).resolve()
    data = load_state(root)
    print(f"state {state_path(root)}")
    print(f"  churn_tokens {data.get('churn_tokens', 0)}")
    print(f"  churn_turns  {data.get('churn_turns', 0)}")
    print(f"  fresh_input  {data.get('fresh_input', 0)}")
    usage = data.get("usage") or {}
    if usage:
        print(f"  this session turns={usage.get('turns', 0)}")
    print(f"  remembered reads {len(data.get('reads') or {})}")
    if data.get("reminder"):
        print(f"  reminder {data['reminder']}")
    return 0


def cmd_mcp_prune(args: argparse.Namespace) -> int:
    """Handle cmd mcp prune."""
    root = Path(args.path).resolve()
    paths = transcript_paths(root, all_projects=False)
    if not paths:
        print("no session transcripts found", file=sys.stderr)
        return 1
    report = analyze(paths, keep_content=False)
    unused, used = classify_servers(root, report)
    if not unused:
        print("no unused MCP servers (or none declared)")
        return 0
    print("unused MCP servers:")
    for name in unused:
        print(f"  {name}")
    if args.apply and not used and not getattr(args, "force", False):
        print("no MCP tool names seen in transcripts — refusing --apply (pass --force to override)",
              file=sys.stderr)
        return 2
    if args.apply:
        path = disable_unused(root, unused)
        print(f"wrote disabledMcpServers → {path}")
    else:
        print("re-run with --apply to write disabledMcpServers")
    return 0


def cmd_budget(args: argparse.Namespace) -> int:
    """Compare a project's measured context against a recommended budget."""
    window = args.window
    if window <= 0:
        print("window must be positive", file=sys.stderr)
        return 1

    plan = {
        "system+tools": int(window * 0.10),
        "autocompact_buffer": int(window * 0.165),
        "always_on_memory": int(window * 0.01),
        "code_map": min(8_000, int(window * 0.04)),
        "working_files": int(window * 0.15),
        "conversation": int(window * 0.40),
    }

    measured: dict[str, int] = {}
    root = Path(args.path).resolve()
    if root.is_dir():
        try:
            report = audit(root, _counter(args), window=window,
                           user_scope=not args.no_user_scope)
            measured["always_on_memory"] = report.always_on
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        codemap = root / "CODEMAP.md"
        if codemap.is_file():
            measured["code_map"] = estimate_tokens(
                codemap.read_text(encoding="utf-8", errors="replace"), ".md"
            )

    print(f"window={window}  project={root}")
    print(f"  {'slice':22} {'budget':>8} {'share':>7} {'measured':>9}  status")
    for key, value in plan.items():
        actual = measured.get(key)
        if actual is None:
            shown, status = "-", ""
        else:
            shown = str(actual)
            status = "OVER" if actual > value else "ok"
        print(f"  {key:22} {value:8} {value / window:6.1%} {shown:>9}  {status}")
    print(f"  {'TOTAL_PLANNED':22} {sum(plan.values()):8} "
          f"{sum(plan.values()) / window:6.1%}")
    if not measured:
        print("\n  (no project measured — pass a path to compare against real files)")
    print("\nRules:")
    print("  - always-on memory is multiplied by every turn; keep it under 1% of window")
    print("  - path-scoped rules and skills load only when needed")
    print("  - prefer @file + line ranges over whole-repo dumps")
    print("  - /clear between unrelated tasks; /compact at breakpoints")
    print("  - cap the code map: acco map . --max-tokens 8000")
    print("  - send noisy logs through: acco filter")
    return 0


def cmd_output(args):
    """Handle cmd output."""
    from .output_store import retrieve
    try:
        sys.stdout.write(retrieve(args.id, args.stream, args.offset, args.limit))
        return 0
    except (OSError, ValueError) as exc:
        print(f"output unavailable: {exc}", file=sys.stderr)
        return 1


def cmd_benchmark(args):
    """Handle cmd benchmark."""
    from .benchmark import evaluate, task_definition_hash
    try:
        if args.print_task_definition_hash:
            payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("manifest must be a JSON object")
            print(task_definition_hash(payload))
            return 0
        if not args.rates:
            raise ValueError("--rates is required unless --print-task-definition-hash is used")
        print(json.dumps(
            evaluate(
                args.manifest,
                args.rates,
                require_publishable=args.require_publishable,
            ),
            indent=2,
        ))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Run the command-line entry point."""
    p = argparse.ArgumentParser(
        prog="acco",
        description="Cut tokens sent to coding AIs (Claude and similar).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_counting(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--exact", action="store_true",
            help="count with the Claude API instead of estimating (needs credentials)",
        )
        parser.add_argument("--model", default=DEFAULT_MODEL,
                            help=f"model for --exact (default {DEFAULT_MODEL})")

    a = sub.add_parser("audit", help="measure what loads into context every turn")
    a.add_argument("path", nargs="?", default=".")
    a.add_argument("--window", type=int, default=200_000)
    a.add_argument("--no-user-scope", action="store_true",
                   help="ignore ~/.claude (project files only)")
    a.add_argument("--probe-mcp", action="store_true",
                   help="measure MCP tool schemas by launching each server")
    a.add_argument("--mcp-timeout", type=int, default=15)
    add_counting(a)
    a.set_defaults(func=cmd_audit)

    o = sub.add_parser("outline", help="signatures of one file instead of all of it")
    o.add_argument("file")
    o.add_argument("--docstrings", action="store_true",
                   help="keep the first docstring line of each symbol (Python only)")
    o.add_argument("-q", "--quiet", action="store_true",
                   help="suppress the savings line on stderr")
    o.add_argument("--no-line-numbers", action="store_true",
                   help="drop the line-number gutter (saves a few tokens, but "
                        "you lose the ranges to read back)")
    o.set_defaults(func=cmd_outline)

    v = sub.add_parser("sessions",
                       help="where tokens actually went, from real transcripts")
    v.add_argument("path", nargs="?", default=".")
    v.add_argument("--all-projects", action="store_true",
                   help="every project, not just this one")
    v.add_argument("--top", type=int, default=8)
    v.add_argument("--rates", help="JSON model-specific USD rates per million tokens")
    v.set_defaults(func=cmd_sessions)

    m = sub.add_parser("map", help="write a compact structural map of a repo")
    m.add_argument("path", nargs="?", default=".")
    m.add_argument("-o", "--out")
    m.add_argument("--max-tokens", type=int, default=None,
                   help="hard cap; lower-priority files are indexed, not expanded")
    m.add_argument("--docstrings", action="store_true",
                   help="keep the first docstring line of each symbol (Python only)")
    m.add_argument("--no-gitignore", action="store_true",
                   help="include files git ignores")
    m.add_argument("--check-stale", action="store_true")
    m.add_argument("--refresh-if-stale", action="store_true")
    m.set_defaults(func=cmd_map)

    e = sub.add_parser("estimate", help="count tokens in a file or stdin")
    e.add_argument("-f", "--file")
    add_counting(e)
    e.set_defaults(func=cmd_estimate)

    f = sub.add_parser("filter", help="compress stdin (logs/tests) for the model")
    f.add_argument("--max-lines", type=int, default=80)
    f.add_argument("--keep-tail", type=int, default=20)
    f.add_argument(
        "--command",
        default="",
        help="original command — enables pytest/jest/git/npm-aware clipping",
    )
    f.set_defaults(func=cmd_filter)

    h = sub.add_parser(
        "hook",
        help="coding-agent hook adapter: guard large Reads + filter noisy tool output",
    )
    h.add_argument(
        "--host",
        choices=["claude", "cursor", "gemini", "qwen", "copilot"],
        default="claude",
        help="hook protocol to serve (default: claude)",
    )
    h.add_argument(
        "--event",
        help="native host event name; required for non-Claude adapters",
    )
    h.set_defaults(
        func=lambda args: hook_main(
            [
                "--host",
                args.host,
                *(
                    ["--event", args.event]
                    if args.event is not None
                    else []
                ),
            ]
        )
    )

    ins = sub.add_parser(
        "install",
        help="write PreToolUse + PostToolUse hooks into .claude/settings.json",
    )
    ins.add_argument("path", nargs="?", default=".")
    ins.add_argument("--user", action="store_true")
    ins.add_argument("--templates", action="store_true")
    ins.set_defaults(func=cmd_install)

    pol = sub.add_parser("policy", help="lifecycle advice from real transcripts")
    pol.add_argument("path", nargs="?", default=".")
    pol.add_argument("--all-projects", action="store_true")
    pol.set_defaults(func=cmd_policy)

    chk = sub.add_parser("check", help="fail CI if always-on context is too fat")
    chk.add_argument("path", nargs="?", default=".")
    chk.add_argument("--window", type=int, default=200_000)
    chk.add_argument("--no-user-scope", action="store_true")
    chk.add_argument("--fail-stale-map", action="store_true")
    add_counting(chk)
    chk.set_defaults(func=cmd_check)

    st = sub.add_parser("status", help="read the on-disk ledger hooks use")
    st.add_argument("path", nargs="?", default=".")
    st.set_defaults(func=cmd_status)

    pr = sub.add_parser("mcp-prune", help="disable MCP servers never called in transcripts")
    pr.add_argument("path", nargs="?", default=".")
    pr.add_argument("--apply", action="store_true")
    pr.add_argument("--force", action="store_true",
                    help="apply even if no MCP tools were observed in transcripts")
    pr.set_defaults(func=cmd_mcp_prune)

    sn = sub.add_parser("snippet", help="extract one symbol instead of the whole file")
    sn.add_argument("file")
    sn.add_argument("symbol")
    sn.add_argument("-q", "--quiet", action="store_true")
    sn.set_defaults(func=cmd_snippet)

    b = sub.add_parser("budget", help="compare a project against a context budget")
    b.add_argument("path", nargs="?", default=".")
    b.add_argument("--window", type=int, default=200_000)
    b.add_argument("--no-user-scope", action="store_true")
    add_counting(b)
    b.set_defaults(func=cmd_budget)

    out = sub.add_parser("output", help="page a saved original command result without re-execution")
    out.add_argument("id")
    out.add_argument("--stream", choices=["stdout", "stderr"], default="stdout")
    out.add_argument("--offset", type=int, default=1)
    out.add_argument("--limit", type=int, default=80)
    out.set_defaults(func=cmd_output)
    prune = sub.add_parser("outputs-prune", help="delete saved command results older than N days")
    prune.add_argument("--days", type=float, default=7)
    def prune_outputs(args):
        from .output_store import prune
        if args.days < 0: p.error("--days must be nonnegative")
        print(f"removed {prune(args.days)} saved outputs")
        return 0
    prune.set_defaults(func=prune_outputs)
    bench = sub.add_parser("benchmark", help="compare paired recorded coding tasks")
    bench.add_argument("manifest")
    bench.add_argument("--rates")
    bench.add_argument(
        "--require-publishable", action="store_true",
        help="require frozen >=20-task, >=3-trial independently verified evidence",
    )
    bench.add_argument(
        "--print-task-definition-hash", action="store_true",
        help="print the hash to freeze before any paid benchmark run",
    )
    bench.set_defaults(func=cmd_benchmark)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
