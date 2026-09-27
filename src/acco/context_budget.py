"""Adaptive whole-context token-budget planning for ACCO."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from collections.abc import Mapping

from .generation_policy import classify_output_task
from .output_budget import adaptive_output_budget

CONTEXT_COMPONENTS = (
    "source",
    "history",
    "memory",
    "tool_results",
    "schemas",
    "reserve",
)

_BASE_WEIGHTS: dict[str, dict[str, float]] = {
    "general": {
        "source": 0.50,
        "history": 0.15,
        "memory": 0.08,
        "tool_results": 0.10,
        "schemas": 0.06,
        "reserve": 0.11,
    },
    "explanation": {
        "source": 0.45,
        "history": 0.18,
        "memory": 0.10,
        "tool_results": 0.08,
        "schemas": 0.05,
        "reserve": 0.14,
    },
    "coding": {
        "source": 0.60,
        "history": 0.10,
        "memory": 0.06,
        "tool_results": 0.10,
        "schemas": 0.05,
        "reserve": 0.09,
    },
    "debugging": {
        "source": 0.50,
        "history": 0.12,
        "memory": 0.05,
        "tool_results": 0.20,
        "schemas": 0.04,
        "reserve": 0.09,
    },
    "review": {
        "source": 0.62,
        "history": 0.10,
        "memory": 0.05,
        "tool_results": 0.08,
        "schemas": 0.04,
        "reserve": 0.11,
    },
    "planning": {
        "source": 0.45,
        "history": 0.15,
        "memory": 0.15,
        "tool_results": 0.07,
        "schemas": 0.04,
        "reserve": 0.14,
    },
}

_HIGH_RISK_RE = re.compile(
    r"\b("
    r"security|secure|vulnerability|auth(?:entication|orization)?|permission|"
    r"cryptograph|encrypt|payment|billing|production|incident|outage|"
    r"data[ -]?loss|destructive|database[ -]?migration|schema[ -]?migration|"
    r"distributed|concurren|race[ -]?condition|deadlock|release|deploy(?:ment)?|"
    r"infrastructure|terraform|kubernetes"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ContextBudgetPlan:
    """Describe a deterministic allocation of one model-context envelope."""

    total_tokens: int
    task: str
    complexity_tier: str
    risk_level: str
    allocations: dict[str, int]
    weights: dict[str, float]
    observed_tokens: dict[str, int]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        """Return a JSON-safe budget decision."""
        return asdict(self)

    def tokens_for(self, component: str) -> int:
        """Return one validated component allocation."""
        if component not in CONTEXT_COMPONENTS:
            raise ValueError(f"unknown context component: {component}")
        return int(self.allocations[component])


def _normalized_weights(
    task: str,
    *,
    complexity_tier: str,
    risk_level: str,
) -> tuple[dict[str, float], list[str]]:
    """Return normalized task/risk/complexity weights."""
    weights = dict(_BASE_WEIGHTS[task])
    reasons = [f"task={task}", f"complexity={complexity_tier}"]

    if complexity_tier in {"complex", "extended"}:
        multiplier = 1.10 if complexity_tier == "complex" else 1.18
        weights["source"] *= multiplier
        weights["history"] *= 1.06
        weights["schemas"] *= 0.94
        reasons.append("complexity_favors_source_and_history")

    if risk_level == "high":
        weights["source"] *= 1.08
        weights["reserve"] *= 1.20
        weights["memory"] *= 0.92
        reasons.append("high_risk_increases_source_and_reserve")

    total = sum(weights.values())
    return ({key: value / total for key, value in weights.items()}, reasons)


def _integer_allocation(weights: Mapping[str, float], total: int) -> dict[str, int]:
    """Convert normalized weights to exact integer allocations."""
    raw = {name: total * float(weights[name]) for name in CONTEXT_COMPONENTS}
    result = {name: int(math.floor(raw[name])) for name in CONTEXT_COMPONENTS}
    remaining = total - sum(result.values())
    ordered = sorted(
        CONTEXT_COMPONENTS,
        key=lambda name: (raw[name] - result[name], name),
        reverse=True,
    )
    for name in ordered[:remaining]:
        result[name] += 1
    return result


def _normalize_observed(observed: Mapping[str, int] | None) -> dict[str, int]:
    """Validate optional observed component sizes."""
    if observed is None:
        return {}
    result: dict[str, int] = {}
    for key, value in observed.items():
        if key not in CONTEXT_COMPONENTS:
            raise ValueError(f"unknown observed context component: {key}")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"observed token count for {key} must be nonnegative")
        result[key] = value
    return result


def _cap_to_observed(
    allocations: dict[str, int],
    observed: dict[str, int],
) -> tuple[dict[str, int], list[str]]:
    """Cap known-demand slices and redistribute unused budget conservatively."""
    result = dict(allocations)
    reclaimed = 0
    reasons: list[str] = []
    for component in ("history", "memory", "tool_results", "schemas"):
        if component not in observed:
            continue
        demand = observed[component]
        if demand < result[component]:
            reclaimed += result[component] - demand
            result[component] = demand
            reasons.append(f"{component}_capped_to_observed")

    if "source" in observed and observed["source"] < result["source"]:
        reclaimed += result["source"] - observed["source"]
        result["source"] = observed["source"]
        reasons.append("source_capped_to_observed")

    if reclaimed:
        # Prefer exact source when there is unknown/unbounded source demand.
        source_room = None
        if "source" in observed:
            source_room = max(0, observed["source"] - result["source"])
        if source_room is None:
            result["source"] += reclaimed
            reclaimed = 0
            reasons.append("unused_budget_redistributed_to_source")
        elif source_room:
            grant = min(source_room, reclaimed)
            result["source"] += grant
            reclaimed -= grant
            reasons.append("unused_budget_redistributed_to_source")

    if reclaimed:
        result["reserve"] += reclaimed
        reasons.append("unused_budget_redistributed_to_reserve")
    return result, reasons


def plan_context_budget(
    prompt: str,
    *,
    total_tokens: int,
    task: str | None = None,
    observed_tokens: Mapping[str, int] | None = None,
) -> ContextBudgetPlan:
    """Allocate one total context budget across ACCO context components."""
    if isinstance(total_tokens, bool) or not isinstance(total_tokens, int):
        raise ValueError("total_tokens must be an integer")
    if total_tokens < 1000:
        raise ValueError("total_tokens must be at least 1000")

    resolved_task = (task or classify_output_task(prompt) or "general").strip().lower()
    if resolved_task not in _BASE_WEIGHTS:
        raise ValueError(f"unsupported context-budget task: {resolved_task}")

    output_budget = adaptive_output_budget(
        prompt,
        task=resolved_task,
        mode="normal",
    )
    risk_matches = sorted({m.group(0).lower() for m in _HIGH_RISK_RE.finditer(prompt)})
    risk_level = "high" if risk_matches else "normal"
    weights, reasons = _normalized_weights(
        resolved_task,
        complexity_tier=output_budget.complexity_tier,
        risk_level=risk_level,
    )
    allocations = _integer_allocation(weights, total_tokens)
    observed = _normalize_observed(observed_tokens)
    allocations, observed_reasons = _cap_to_observed(allocations, observed)
    reasons.extend(observed_reasons)
    if risk_matches:
        reasons.append("risk=" + ",".join(risk_matches[:6]))

    if sum(allocations.values()) != total_tokens:
        raise RuntimeError("context-budget allocator lost token conservation")

    return ContextBudgetPlan(
        total_tokens=total_tokens,
        task=resolved_task,
        complexity_tier=output_budget.complexity_tier,
        risk_level=risk_level,
        allocations=allocations,
        weights=weights,
        observed_tokens=observed,
        reasons=tuple(reasons),
    )
