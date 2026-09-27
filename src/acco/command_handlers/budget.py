"""CLI for deterministic whole-context budget planning."""

from __future__ import annotations

import argparse
import json
import sys

from ..context_budget import CONTEXT_COMPONENTS, plan_context_budget


def context_budget_main(argv: list[str]) -> int:
    """Plan one total model-context envelope across ACCO components."""
    parser = argparse.ArgumentParser(prog="acco context-budget")
    parser.add_argument("prompt", nargs="?", help="task prompt; reads stdin when omitted")
    parser.add_argument("--total-tokens", type=int, required=True)
    parser.add_argument(
        "--task",
        choices=["general", "explanation", "planning", "coding", "debugging", "review"],
    )
    for component in CONTEXT_COMPONENTS:
        if component == "reserve":
            continue
        parser.add_argument(
            f"--observed-{component.replace('_', '-')}",
            type=int,
            dest=f"observed_{component}",
        )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    observed = {
        component: getattr(args, f"observed_{component}")
        for component in CONTEXT_COMPONENTS
        if component != "reserve"
        and getattr(args, f"observed_{component}", None) is not None
    }
    try:
        plan = plan_context_budget(
            prompt,
            total_tokens=args.total_tokens,
            task=args.task,
            observed_tokens=observed,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = plan.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print("ACCO CONTEXT BUDGET")
    print(
        f"task={plan.task} complexity={plan.complexity_tier} "
        f"risk={plan.risk_level} total={plan.total_tokens}"
    )
    for component in CONTEXT_COMPONENTS:
        tokens = plan.allocations[component]
        print(f"{component:<13} {tokens:>7}  ({tokens / plan.total_tokens:>6.1%})")
    if plan.reasons:
        print("reasons: " + ", ".join(plan.reasons))
    return 0
