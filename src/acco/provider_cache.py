"""Provider-native prompt-cache planning and observed-cache accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any

from .efficiency.store import append_event
from .prefix_cache import PrefixPlan

# Relative cost factors are planning assumptions, not provider billing claims.
# They can be overridden per call. Observed provider counters remain authoritative.
_DEFAULT_FACTORS = {
    "anthropic": (1.25, 0.10, "explicit-breakpoint"),
    "openai": (1.00, 0.50, "automatic"),
    "gemini": (1.00, 0.25, "explicit-context-resource"),
    "bedrock": (1.25, 0.10, "explicit-breakpoint"),
}


@dataclass(frozen=True)
class ProviderCachePlan:
    """Describe whether a stable prefix is economically worth caching/reusing."""

    provider: str
    model: str | None
    eligible: bool
    strategy: str
    stable_prefix_tokens: int
    expected_reuses: int
    cache_write_factor: float
    cache_read_factor: float
    uncached_cost_units: float
    cached_cost_units: float
    relative_savings: float | None
    break_even_reuses: int | None
    epoch_key: str
    reason: str
    evidence_basis: str = "planned"

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible cache planning metadata."""
        return asdict(self)


def _finite_positive(value: float, name: str) -> float:
    """Validate a positive finite relative cost factor."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def plan_provider_cache(
    provider: str,
    prefix: PrefixPlan,
    *,
    model: str | None = None,
    expected_reuses: int = 2,
    min_prefix_tokens: int = 1024,
    cache_write_factor: float | None = None,
    cache_read_factor: float | None = None,
) -> ProviderCachePlan:
    """Plan prompt-cache economics without claiming a future cache hit."""
    normalized = str(provider or "generic").strip().lower()
    expected_reuses = max(0, int(expected_reuses))
    if min_prefix_tokens < 0:
        raise ValueError("min_prefix_tokens must be nonnegative")
    defaults = _DEFAULT_FACTORS.get(normalized)
    if defaults is None:
        return ProviderCachePlan(
            provider=normalized,
            model=model,
            eligible=False,
            strategy="unsupported",
            stable_prefix_tokens=prefix.stable_tokens,
            expected_reuses=expected_reuses,
            cache_write_factor=1.0,
            cache_read_factor=1.0,
            uncached_cost_units=float(prefix.stable_tokens * (1 + expected_reuses)),
            cached_cost_units=float(prefix.stable_tokens * (1 + expected_reuses)),
            relative_savings=None,
            break_even_reuses=None,
            epoch_key=prefix.epoch_key,
            reason="provider_has_no_registered_cache_plan",
        )
    default_write, default_read, strategy = defaults
    write_factor = _finite_positive(
        cache_write_factor if cache_write_factor is not None else default_write,
        "cache_write_factor",
    )
    read_factor = _finite_positive(
        cache_read_factor if cache_read_factor is not None else default_read,
        "cache_read_factor",
    )
    tokens = max(0, int(prefix.stable_tokens))
    uncached = float(tokens * (1 + expected_reuses))
    cached = float(tokens * write_factor + tokens * expected_reuses * read_factor)
    relative = 1.0 - cached / uncached if uncached > 0 else None
    denominator = 1.0 - read_factor
    break_even = None
    if denominator > 0:
        break_even = max(
            0,
            math.ceil(max(0.0, write_factor - 1.0) / denominator),
        )
    eligible = (
        tokens >= int(min_prefix_tokens)
        and expected_reuses >= (break_even or 0)
        and relative is not None
        and relative > 0
    )
    reason = (
        "cache_plan_positive"
        if eligible
        else "prefix_too_small"
        if tokens < int(min_prefix_tokens)
        else "expected_reuse_below_break_even"
        if break_even is not None and expected_reuses < break_even
        else "cache_not_economic_under_assumptions"
    )
    return ProviderCachePlan(
        provider=normalized,
        model=model,
        eligible=eligible,
        strategy=strategy,
        stable_prefix_tokens=tokens,
        expected_reuses=expected_reuses,
        cache_write_factor=write_factor,
        cache_read_factor=read_factor,
        uncached_cost_units=uncached,
        cached_cost_units=cached,
        relative_savings=relative,
        break_even_reuses=break_even,
        epoch_key=prefix.epoch_key,
        reason=reason,
    )


def record_cache_plan(root: Path, plan: ProviderCachePlan) -> None:
    """Persist content-free planned cache economics separately from observations."""
    try:
        append_event(
            root,
            {
                "kind": "cache_plan",
                "feature": "provider_cache",
                "provider": plan.provider,
                "model": plan.model,
                "eligible": plan.eligible,
                "strategy": plan.strategy,
                "stable_prefix_tokens": plan.stable_prefix_tokens,
                "expected_reuses": plan.expected_reuses,
                "relative_savings": plan.relative_savings,
                "break_even_reuses": plan.break_even_reuses,
                "epoch_key": plan.epoch_key,
                "evidence_basis": "planned",
            },
        )
    except OSError:
        pass


def observed_cache_evidence(provider: str, usage: dict[str, Any]) -> dict[str, Any]:
    """Return content-free observed cache counters without inferring missing hits."""
    created = usage.get("cache_creation_input_tokens")
    read = usage.get("cache_read_input_tokens")
    return {
        "provider": str(provider).strip().lower(),
        "cache_creation_input_tokens": int(created) if isinstance(created, int) else 0,
        "cache_read_input_tokens": int(read) if isinstance(read, int) else 0,
        "cache_observed": bool(
            isinstance(created, int) and created > 0
            or isinstance(read, int) and read > 0
        ),
        "evidence_basis": "provider-observed",
    }
