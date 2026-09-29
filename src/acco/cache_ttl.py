"""Provider cache-TTL learning from content-free observed hit/miss evidence."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import time
from typing import Any

from .efficiency.store import append_event, load_events


def record_cache_observation(
    root: Path,
    *,
    provider: str,
    model: str,
    epoch_key: str,
    reuse_mode: str,
    cache_read_tokens: int,
    cache_creation_tokens: int = 0,
    now: int | None = None,
) -> dict[str, Any]:
    """Record one provider-observed cache outcome and conservatively attribute misses."""
    timestamp = int(time.time()) if now is None else int(now)
    normalized_provider = str(provider or "generic").strip().lower()
    normalized_model = str(model or "unknown")[:160]
    epoch = str(epoch_key or "default")[:64]
    prior = None
    for event in reversed(load_events(root)):
        if (
            event.get("kind") == "cache_ttl_observation"
            and event.get("provider") == normalized_provider
            and event.get("model") == normalized_model
            and event.get("epoch_key") == epoch
        ):
            prior = event
            break

    idle_seconds = None
    if isinstance(prior, dict):
        prior_time = prior.get("observed_at")
        if not isinstance(prior_time, int):
            prior_time = prior.get("recorded_at")
        if isinstance(prior_time, int):
            idle_seconds = max(0, timestamp - int(prior_time))

    read = max(0, int(cache_read_tokens or 0))
    created = max(0, int(cache_creation_tokens or 0))
    if read > 0:
        outcome = "hit"
        reason = "provider_observed_cache_read"
    elif prior is None:
        outcome = "miss"
        reason = "cold_start"
    elif reuse_mode == "exact" and prior.get("outcome") == "hit":
        outcome = "miss"
        reason = "ttl_expiry"
    elif reuse_mode in {"exact", "extended"}:
        outcome = "miss"
        reason = "stable_prefix_no_cache_read"
    else:
        outcome = "miss"
        reason = "prefix_change"

    event = {
        "kind": "cache_ttl_observation",
        "feature": "provider_cache_ttl",
        "observed_at": timestamp,
        "provider": normalized_provider,
        "model": normalized_model,
        "epoch_key": epoch,
        "reuse_mode": str(reuse_mode or "miss"),
        "outcome": outcome,
        "reason": reason,
        "idle_seconds": idle_seconds,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": created,
        "evidence_basis": "provider-observed",
    }
    append_event(root, event)
    return {"recorded_at": timestamp, **event}


def cache_ttl_report(root: Path) -> dict[str, Any]:
    """Infer conservative per-provider/model TTL bounds from observed cache outcomes."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for event in load_events(root):
        if event.get("kind") != "cache_ttl_observation":
            continue
        provider = event.get("provider")
        model = event.get("model")
        if isinstance(provider, str) and isinstance(model, str):
            groups[(provider, model)].append(event)

    estimates: list[dict[str, Any]] = []
    for (provider, model), events in sorted(groups.items()):
        hit_idles = [
            int(event["idle_seconds"])
            for event in events
            if event.get("outcome") == "hit"
            and isinstance(event.get("idle_seconds"), int)
        ]
        expiry_idles = [
            int(event["idle_seconds"])
            for event in events
            if event.get("reason") == "ttl_expiry"
            and isinstance(event.get("idle_seconds"), int)
        ]
        lower = max(hit_idles) if hit_idles else None
        upper_candidates = [
            value
            for value in expiry_idles
            if lower is None or value >= lower
        ]
        upper = min(upper_candidates) if upper_candidates else None
        observed_hits = sum(event.get("outcome") == "hit" for event in events)
        learned = (
            upper
            if lower is not None
            and upper is not None
            and observed_hits >= 2
            and upper >= lower
            else None
        )
        estimates.append(
            {
                "provider": provider,
                "model": model,
                "observations": len(events),
                "hits": observed_hits,
                "misses": sum(event.get("outcome") == "miss" for event in events),
                "hit_lower_bound_seconds": lower,
                "expiry_upper_bound_seconds": upper,
                "learned_ttl_seconds": learned,
                "qualified": learned is not None,
                "evidence_basis": (
                    "provider-observed cache counters with ACCO-inferred exact-prefix "
                    "expiry classification"
                ),
            }
        )
    return {
        "schema": 1,
        "estimates": estimates,
        "policy": (
            "A learned TTL requires >=2 observed hits plus an exact-prefix miss "
            "after a prior hit. The conservative upper miss bound is reported."
        ),
    }


def learned_ttl_seconds(root: Path, provider: str, model: str | None) -> int | None:
    """Return one qualified learned TTL without falling back to guessed defaults."""
    wanted_provider = str(provider or "generic").strip().lower()
    wanted_model = str(model or "unknown")
    for item in cache_ttl_report(root)["estimates"]:
        if item["provider"] == wanted_provider and item["model"] == wanted_model:
            value = item.get("learned_ttl_seconds")
            return int(value) if isinstance(value, int) else None
    return None
