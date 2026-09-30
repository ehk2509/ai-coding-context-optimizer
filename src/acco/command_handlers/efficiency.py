"""CLI handlers for session continuity and local efficiency telemetry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ..cache_economics import assess_context_rewrite
from ..cache_ttl import cache_ttl_report
from ..efficiency import continuity_report, dashboard_report
from ..estimate import Counter, DEFAULT_MODEL
from ..efficiency.advisor import advisor_report
from ..unified_audit import unified_audit_report
from ..efficiency.dashboard import render_dashboard_html
from ..observability import observability_report, prometheus_metrics
from ..output_holdout import output_holdout_report
from ..tool_field_learning import field_learning_report


def _tokens(value: object) -> str:
    """Format a token count for compact terminal output."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "0"
    number = int(value)
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}K"
    return str(number)



def audit_main(argv: list[str]) -> int:
    """Run one consolidated audit across context, retrieval, output, and host layers."""
    parser = argparse.ArgumentParser(prog="acco audit")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--window", type=int, default=200_000)
    parser.add_argument(
        "--no-user-scope",
        "--project-only",
        dest="project_only",
        action="store_true",
        help="ignore user-scope Claude instructions",
    )
    parser.add_argument("--probe-mcp", action="store_true")
    parser.add_argument("--mcp-timeout", type=int, default=15)
    parser.add_argument("--client")
    parser.add_argument("--rates")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-processor-tokens", type=int, default=100)
    parser.add_argument("--exact", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = unified_audit_report(
            Path(args.path),
            days=args.days,
            window=args.window,
            user_scope=not args.project_only,
            rates_path=(
                args.rates
                if args.rates == "builtin"
                else Path(args.rates)
                if args.rates
                else None
            ),
            client=args.client,
            top=args.top,
            min_processor_tokens=args.min_processor_tokens,
            probe_mcp=args.probe_mcp,
            mcp_timeout=args.mcp_timeout,
            counter=Counter(exact=args.exact, model=args.model),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    context = report["context"]
    efficiency = report["efficiency"]
    semantic = report["retrieval"]["semantic"]
    fastpath = report["fastpath"]
    processors = report["processor_coverage"]
    recovery = report["recovery"]
    print("ACCO AUDIT")
    print(f"project: {report['root']}")
    share = context["window_share"]
    share_text = f"{share:.1%}" if isinstance(share, (int, float)) else "n/a"
    print(
        f"context: {context['always_on_tokens']:,} always-on tokens "
        f"({share_text} of {context['window']:,})"
    )
    if context["mcp_servers_configured"]:
        print(
            "mcp: "
            f"{len(context['mcp_servers_configured'])} configured"
            + ("; schemas probed" if context["mcp_probe"] else "; use --probe-mcp to measure")
        )
    score = efficiency.get("score") or {}
    grade = score.get("grade") or "insufficient evidence"
    print(
        "efficiency: "
        f"{float(score.get('percent') or 0):.1f}% ({grade}), "
        f"coverage {float(score.get('coverage') or 0):.0%}"
    )
    print(
        "retrieval: "
        f"{semantic.get('chunks', 0)} semantic chunks; "
        f"backend={semantic.get('backend', 'unknown')}"
    )
    print(
        "fastpath: "
        f"{fastpath.get('backend', 'python')} "
        f"({len(fastpath.get('capabilities', []))} accelerated primitives)"
    )
    coverage = processors.get("specialized_coverage")
    if coverage is None:
        print("processors: no eligible Bash transcript evidence")
    else:
        print(
            "processors: "
            f"{coverage:.1%} of analyzed output tokens specialized; "
            f"{processors.get('generic_output_tokens', 0):,} generic tokens"
        )
    print(
        "recovery: "
        f"{recovery.get('records', 0)} exact payload(s), "
        f"{recovery.get('used_bytes', 0):,}/{recovery.get('capacity_bytes', 0):,} bytes"
    )
    if report["client_capabilities"]:
        client = report["client_capabilities"]["client"]
        print(f"client: {client['client']} — {client['note']}")
    print("next actions:")
    if not report["recommendations"]:
        print("  none from current evidence")
    for item in report["recommendations"]:
        print(
            f"  [{item['priority']}] {item['id']} — "
            f"{item['evidence']} — {item['action']}"
        )
    print(
        "evidence: operational measurements/estimates only; "
        "cost-per-success still requires paired evaluation"
    )
    return 0



def learn_main(argv: list[str]) -> int:
    """Rank token sinks and optimization opportunities from historical sessions."""
    from ..learn import learn_report

    parser = argparse.ArgumentParser(prog="acco learn")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument(
        "--project-only",
        action="store_true",
        help="exclude user-scope Claude instructions from always-on context analysis",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = learn_report(
            Path(args.path),
            days=args.days,
            top=args.top,
            user_scope=not args.project_only,
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    usage = report["usage"]
    print(f"ACCO LEARN — {report['window_days']} days")
    print(
        f"sessions: {report['sessions']}; turns: {report['turns']}; "
        f"transcripts: {report['transcripts']}"
    )
    print("provider usage observed:")
    print(f"  fresh input        {_tokens(usage['input_tokens'])}")
    print(f"  cache creation     {_tokens(usage['cache_creation_input_tokens'])}")
    print(f"  cache read         {_tokens(usage['cache_read_input_tokens'])}")
    print(f"  output             {_tokens(usage['output_tokens'])}")
    print(f"  cache hit rate     {usage['cache_hit_rate']:.1%}")

    print("largest estimated tool-result sources:")
    rows = report["tool_results"]["by_tool"]
    if not rows:
        print("  none")
    for row in rows:
        print(
            f"  {row['tool']:<18} {_tokens(row['estimated_tokens']):>8} "
            f"across {row['calls']} call(s)"
        )

    print("ranked opportunities:")
    if not report["opportunities"]:
        print("  none from current evidence")
    for index, item in enumerate(report["opportunities"], start=1):
        tokens = item["estimated_tokens_at_stake"]
        stake = f" (~{_tokens(tokens)} tokens)" if tokens is not None else ""
        print(f"  {index}. {item['title']}{stake}")
        print(f"     evidence: {item['evidence']}")
        print(f"     action:   {item['action']}")
        print(f"     caution:  {item['caution']}")

    print(
        "evidence: provider counters are measured; tool-result and opportunity "
        "sizes are estimates; no task-success or savings claim is made"
    )
    return 0


def dashboard_main(argv: list[str]) -> int:
    """Show local operational savings, continuity, and waste telemetry."""
    parser = argparse.ArgumentParser(prog="acco dashboard")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--html",
        metavar="FILE",
        help="write a self-contained local HTML dashboard",
    )
    args = parser.parse_args(argv)
    try:
        report = dashboard_report(Path(args.path), days=args.days)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.html:
        destination = Path(args.html).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            render_dashboard_html(report),
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    savings = report["savings"]
    behavior = report["behavior"]
    continuity = report["continuity"]
    usage = report["billed_usage"]
    print(f"ACCO DASHBOARD — {report['window_days']} days")
    print(
        "estimated tool-context saved: "
        + _tokens(savings["estimated_tool_context_tokens"])
        + " tokens"
    )
    for feature, tokens in savings["by_feature"].items():
        print(f"  {feature:<22} {_tokens(tokens):>8}")
    print(f"continuity restores: {continuity['restores']}")
    print(f"tracked sessions:    {continuity['tracked_sessions']}")
    print(f"behavior signals:    {behavior['events']}")
    for feature, count in behavior["signals"].items():
        print(f"  {feature:<22} {count:>8}")
    print("billed usage observed:")
    print(f"  input              {_tokens(usage.get('input_tokens')):>8}")
    print(f"  cache creation     {_tokens(usage.get('cache_creation_input_tokens')):>8}")
    print(f"  cache read         {_tokens(usage.get('cache_read_input_tokens')):>8}")
    print(f"  output             {_tokens(usage.get('output_tokens')):>8}")
    provider_routes = report.get("provider_model_routing", {})
    if provider_routes.get("decisions"):
        projected = provider_routes.get("mean_projected_savings_fraction")
        projected_text = (
            f"; mean projected switch savings {float(projected):.1%}"
            if isinstance(projected, (int, float)) and not isinstance(projected, bool)
            else ""
        )
        print(
            "provider model routing: "
            f"{provider_routes.get('applied', 0)} applied / "
            f"{provider_routes.get('decisions', 0)} decision(s)"
            f"{projected_text}"
        )
    provider_usage = report.get("provider_usage", {})
    if provider_usage.get("calls"):
        print("provider boundary observed (separate; not merged above):")
        print(f"  calls              {provider_usage.get('calls', 0):>8}")
        print(f"  input              {_tokens(provider_usage.get('input_tokens')):>8}")
        print(f"  cache read         {_tokens(provider_usage.get('cache_read_input_tokens')):>8}")
        print(f"  output             {_tokens(provider_usage.get('output_tokens')):>8}")
        for provider, count in provider_usage.get("by_provider", {}).items():
            print(f"  {provider:<18} {count:>8} call(s)")
    print("note: local savings are operational estimates, not a cost/success claim")
    if args.html:
        print(f"html: {Path(args.html).expanduser().resolve()}")
    return 0



def cost_advisor_main(argv: list[str]) -> int:
    """Show measured local cost intelligence and prioritized efficiency actions."""
    parser = argparse.ArgumentParser(prog="acco cost-advisor")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument(
        "--rates",
        help="pricing source: builtin or an explicit exact-model JSON file",
    )
    parser.add_argument(
        "--project-only",
        action="store_true",
        help="exclude user-scope Claude instructions from the context audit",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = advisor_report(
            Path(args.path),
            days=args.days,
            rates_path=(
                args.rates
                if args.rates == "builtin"
                else Path(args.rates)
                if args.rates
                else None
            ),
            user_scope=not args.project_only,
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    score = report["score"]
    grade = score["grade"] or "insufficient evidence"
    print(f"ACCO COST ADVISOR — {report['window_days']} days")
    print(
        f"efficiency score: {score['percent']:.1f}% ({grade}); "
        f"evidence coverage {score['coverage']:.0%}"
    )
    print(f"always-on context: {_tokens(report['context']['always_on_tokens'])} tokens")
    print(
        "estimated tool-context saved: "
        f"{_tokens(report['savings']['estimated_tool_context_tokens'])} tokens"
    )
    cost = report["cost"]
    if cost["usd"] is not None:
        print(f"observed usage cost: USD {cost['usd']:.4f} (complete)")
    elif cost["priced_usd"] is not None:
        print(
            f"observed usage cost: USD {cost['priced_usd']:.4f} partial "
            f"({cost['priced_turns']}/{cost['measured_turns']} turns priced)"
        )
    else:
        print("observed usage cost: not priced")
    print("score breakdown:")
    for category in score["categories"]:
        if category["available"]:
            print(
                f"  {category['name']:<25} "
                f"{category['score']:>5}/{category['weight']}"
            )
        else:
            print(f"  {category['name']:<25}   n/a  ({category['reason']})")
    print("next actions:")
    if not report["recommendations"]:
        print("  none from current evidence")
    for item in report["recommendations"]:
        print(
            f"  [{item['priority']}] {item['action']} "
            f"— {item['evidence']}"
        )
    print(
        "evidence: measured usage/context is separate from estimated savings; "
        "no task-success or end-to-end cost claim"
    )
    return 0



def tool_fields_main(argv: list[str]) -> int:
    """Show locally learned structured tool-field importance."""
    parser = argparse.ArgumentParser(prog="acco tool-fields")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = field_learning_report(Path(args.path), limit=args.limit)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print("ACCO TOOL-FIELD LEARNING")
    print(f"tools observed: {report['tools']}")
    if not report["fields"]:
        print("no retrieval-qualified field evidence")
    for item in report["fields"]:
        print(
            f"{item['tool']}: {item['field_path']} "
            f"retrieved={item['retrievals']}/{item['exposures']} "
            f"confidence={item['confidence']:.0%}"
        )
    print("privacy: structural field paths/counters only; no field values stored")
    return 0


def cache_ttl_main(argv: list[str]) -> int:
    """Show cache-TTL bounds learned from provider-observed cache counters."""
    parser = argparse.ArgumentParser(prog="acco cache-ttl")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = cache_ttl_report(Path(args.path))
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print("ACCO CACHE TTL")
    if not report["estimates"]:
        print("no provider cache observations")
    for item in report["estimates"]:
        learned = item["learned_ttl_seconds"]
        learned_text = f"{learned}s" if isinstance(learned, int) else "unqualified"
        print(
            f"{item['provider']}/{item['model']}: "
            f"hits={item['hits']} misses={item['misses']} "
            f"lower={item['hit_lower_bound_seconds']} "
            f"upper={item['expiry_upper_bound_seconds']} "
            f"ttl={learned_text}"
        )
    print(
        "evidence: cache counters are provider-observed; ttl_expiry is inferred "
        "only when an exact reused prefix stops producing cache-read tokens"
    )
    return 0


def output_holdout_main(argv: list[str]) -> int:
    """Report randomized provider-observed output-token holdout evidence."""
    parser = argparse.ArgumentParser(prog="acco output-holdout")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = output_holdout_report(
            Path(args.path),
            bootstrap_samples=args.bootstrap_samples,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print("ACCO OUTPUT HOLDOUT")
    reduction = report["measured_output_token_reduction"]
    if reduction is None:
        print("measured reduction: insufficient matched control/treatment evidence")
    else:
        print(f"measured reduction: {reduction:.1%}")
    ci = report["ci95"]
    if isinstance(ci, list) and len(ci) == 2:
        print(f"95% bootstrap CI: {ci[0]:.1%} .. {ci[1]:.1%}")
    print(f"matched epoch weight: {report['matched_epoch_weight']}")
    print(
        "boundary: randomized output-token evidence only; response quality and "
        "cost-per-success still require paired evaluation"
    )
    return 0


def observability_main(argv: list[str]) -> int:
    """Show local provider/framework operational metrics or Prometheus text."""
    parser = argparse.ArgumentParser(prog="acco observability")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--prometheus", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.path)
    try:
        if args.prometheus:
            sys.stdout.write(prometheus_metrics(root, days=args.days))
            return 0
        report = observability_report(root, days=args.days)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"ACCO OBSERVABILITY — {report['window_days']} days")
    if not report["providers"]:
        print("provider boundary: no observations")
    for provider, item in report["providers"].items():
        p95 = item["latency_ms_p95"]
        p95_text = f"{p95:.1f}ms" if isinstance(p95, (int, float)) else "n/a"
        print(
            f"provider {provider}: calls={item['calls']} "
            f"transformed={item['transformed']} p95={p95_text} "
            f"context_removed~{item['estimated_context_tokens_removed']}"
        )
    for key, item in report["frameworks"].items():
        print(
            f"framework {key}: calls={item['calls']} failures={item['failures']} "
            f"context_removed~{item['estimated_context_tokens_removed']}"
        )
    print(report["evidence"])
    return 0


def continuity_main(argv: list[str]) -> int:
    """Inspect the latest structured continuity checkpoint."""
    parser = argparse.ArgumentParser(prog="acco continuity")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = continuity_report(Path(args.path))
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print("ACCO CONTINUITY")
    if not report["available"]:
        print("checkpoint: none")
        return 0
    print(f"task: {report['task'] or 'general'}")
    files = [
        item.get("path")
        for item in report["working_files"]
        if isinstance(item, dict) and item.get("path")
    ]
    print("working files: " + (", ".join(files) if files else "none"))
    validations = [
        f"{item.get('kind')}={item.get('status')}"
        for item in report["validations"]
        if isinstance(item, dict)
    ]
    print("validation: " + ("; ".join(validations) if validations else "none"))
    failures = [
        str(item.get("label"))
        for item in report["failures"]
        if isinstance(item, dict) and item.get("label")
    ]
    print("recent failures: " + ("; ".join(failures) if failures else "none"))
    return 0



def cache_economics_main(argv: list[str]) -> int:
    """Estimate whether one context rewrite is cheaper after cache effects."""
    parser = argparse.ArgumentParser(prog="acco cache-economics")
    parser.add_argument("--original-frontier-tokens", type=int, required=True)
    parser.add_argument("--replacement-frontier-tokens", type=int, required=True)
    parser.add_argument("--cached-prefix-tokens", type=int, default=0)
    parser.add_argument("--invalidates-cached-prefix", action="store_true")
    parser.add_argument("--expected-reuses", type=int, default=1)
    parser.add_argument("--cache-write-factor", type=float, default=1.25)
    parser.add_argument("--cache-read-factor", type=float, default=0.10)
    parser.add_argument("--min-relative-savings", type=float, default=0.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        decision = assess_context_rewrite(
            original_frontier_tokens=args.original_frontier_tokens,
            replacement_frontier_tokens=args.replacement_frontier_tokens,
            cached_prefix_tokens=args.cached_prefix_tokens,
            invalidates_cached_prefix=args.invalidates_cached_prefix,
            expected_reuses=args.expected_reuses,
            cache_write_factor=args.cache_write_factor,
            cache_read_factor=args.cache_read_factor,
            min_relative_savings=args.min_relative_savings,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = decision.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    verdict = "ACCEPT" if decision.accepted else "PRESERVE"
    print(f"CACHE ECONOMICS: {verdict}")
    print(f"original relative cost:    {decision.original_cost:.2f}")
    print(f"replacement relative cost: {decision.replacement_cost:.2f}")
    if decision.relative_savings is not None:
        print(f"relative savings:          {decision.relative_savings:.2%}")
    print(
        "cached prefix: "
        f"{decision.cached_prefix_tokens} tokens; "
        f"invalidated={decision.invalidates_cached_prefix}"
    )
    return 0
