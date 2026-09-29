"""Content-free provider/framework observability for ACCO runtime surfaces."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import time
from typing import Any

from .efficiency.store import append_event, load_events


def record_provider_request(
    root: Path,
    *,
    provider: str,
    shape: str,
    model: str | None,
    status: int,
    latency_ms: float,
    changed: bool,
    original_tokens: int,
    output_tokens: int,
    recovery_handles: int,
) -> None:
    """Record one provider-boundary request without storing request/response content."""
    append_event(
        root,
        {
            "kind": "provider_request",
            "feature": "provider_observability",
            "provider": str(provider or "generic").lower(),
            "shape": str(shape or "unknown")[:80],
            "model": str(model or "unknown")[:160],
            "status": int(status),
            "latency_ms": max(0.0, float(latency_ms)),
            "changed": bool(changed),
            "original_tokens": max(0, int(original_tokens or 0)),
            "output_tokens": max(0, int(output_tokens or 0)),
            "recovery_handles": max(0, int(recovery_handles or 0)),
        },
    )


def record_framework_operation(
    root: Path,
    *,
    framework: str,
    operation: str,
    original_tokens: int,
    output_tokens: int,
    latency_ms: float,
    changed: bool,
    success: bool = True,
) -> None:
    """Record one SDK/framework optimization operation using only bounded metadata."""
    append_event(
        root,
        {
            "kind": "framework_operation",
            "feature": "framework_observability",
            "framework": str(framework or "sdk")[:80],
            "operation": str(operation or "unknown")[:80],
            "original_tokens": max(0, int(original_tokens or 0)),
            "output_tokens": max(0, int(output_tokens or 0)),
            "latency_ms": max(0.0, float(latency_ms)),
            "changed": bool(changed),
            "success": bool(success),
        },
    )


def _percentile(values: list[float], q: float) -> float | None:
    """Return a simple nearest-rank percentile for bounded operational telemetry."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[index]


def observability_report(root: Path, *, days: int = 7) -> dict[str, Any]:
    """Aggregate local provider/framework runtime metrics without double-counting usage."""
    if days <= 0:
        raise ValueError("days must be positive")
    since = int(time.time()) - int(days) * 86400
    events = load_events(root, since=since)

    provider_calls = Counter()
    provider_status = Counter()
    provider_latency: dict[str, list[float]] = defaultdict(list)
    provider_input = Counter()
    provider_output = Counter()
    provider_recovery = Counter()
    provider_transformed = Counter()

    framework_calls = Counter()
    framework_latency: dict[str, list[float]] = defaultdict(list)
    framework_saved = Counter()
    framework_failures = Counter()

    cache = Counter()
    holdout = Counter()

    for event in events:
        kind = event.get("kind")
        if kind == "provider_request":
            provider = str(event.get("provider") or "generic")
            provider_calls[provider] += 1
            status = event.get("status")
            if isinstance(status, int):
                provider_status[f"{provider}:{status // 100}xx"] += 1
            latency = event.get("latency_ms")
            if isinstance(latency, (int, float)) and not isinstance(latency, bool):
                provider_latency[provider].append(float(latency))
            before = event.get("original_tokens")
            after = event.get("output_tokens")
            if isinstance(before, int) and not isinstance(before, bool):
                provider_input[provider] += before
            if isinstance(after, int) and not isinstance(after, bool):
                provider_output[provider] += after
            if event.get("changed") is True:
                provider_transformed[provider] += 1
            handles = event.get("recovery_handles")
            if isinstance(handles, int) and not isinstance(handles, bool):
                provider_recovery[provider] += handles

        elif kind == "framework_operation":
            framework = str(event.get("framework") or "sdk")
            operation = str(event.get("operation") or "unknown")
            key = f"{framework}:{operation}"
            framework_calls[key] += 1
            latency = event.get("latency_ms")
            if isinstance(latency, (int, float)) and not isinstance(latency, bool):
                framework_latency[key].append(float(latency))
            before = event.get("original_tokens")
            after = event.get("output_tokens")
            if (
                isinstance(before, int)
                and isinstance(after, int)
                and not isinstance(before, bool)
                and not isinstance(after, bool)
            ):
                framework_saved[key] += max(0, before - after)
            if event.get("success") is False:
                framework_failures[key] += 1

        elif kind == "cache_ttl_observation":
            cache["observations"] += 1
            cache[str(event.get("outcome") or "unknown")] += 1
            if event.get("reason") == "ttl_expiry":
                cache["ttl_expiry"] += 1
        elif kind == "output_holdout_observation":
            holdout["observations"] += 1
            holdout[str(event.get("arm") or "unknown")] += 1

    providers = {}
    for provider in sorted(provider_calls):
        latencies = provider_latency[provider]
        providers[provider] = {
            "calls": provider_calls[provider],
            "transformed": provider_transformed[provider],
            "original_tokens": provider_input[provider],
            "forwarded_tokens": provider_output[provider],
            "estimated_context_tokens_removed": max(
                0, provider_input[provider] - provider_output[provider]
            ),
            "recovery_handles": provider_recovery[provider],
            "latency_ms_p50": _percentile(latencies, 0.50),
            "latency_ms_p95": _percentile(latencies, 0.95),
            "status_classes": {
                key.split(":", 1)[1]: value
                for key, value in sorted(provider_status.items())
                if key.startswith(provider + ":")
            },
        }

    frameworks = {}
    for key in sorted(framework_calls):
        latencies = framework_latency[key]
        frameworks[key] = {
            "calls": framework_calls[key],
            "failures": framework_failures[key],
            "estimated_context_tokens_removed": framework_saved[key],
            "latency_ms_p50": _percentile(latencies, 0.50),
            "latency_ms_p95": _percentile(latencies, 0.95),
        }

    return {
        "schema": 1,
        "window_days": days,
        "providers": providers,
        "frameworks": frameworks,
        "cache_ttl": dict(cache),
        "output_holdout": dict(holdout),
        "evidence": (
            "Provider/framework counters are local operational measurements. "
            "Token removal is not a task-success or billed-savings claim."
        ),
    }


def prometheus_metrics(root: Path, *, days: int = 7) -> str:
    """Render a small Prometheus text exposition from the local observability report."""
    report = observability_report(root, days=days)
    lines = [
        "# HELP acco_provider_requests_total Provider-boundary requests observed by ACCO.",
        "# TYPE acco_provider_requests_total counter",
    ]
    for provider, data in report["providers"].items():
        label = provider.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(
            f'acco_provider_requests_total{{provider="{label}"}} {data["calls"]}'
        )
        lines.append(
            f'acco_provider_transformed_total{{provider="{label}"}} {data["transformed"]}'
        )
        lines.append(
            f'acco_provider_context_tokens_removed_total{{provider="{label}"}} '
            f'{data["estimated_context_tokens_removed"]}'
        )
        if data["latency_ms_p95"] is not None:
            lines.append(
                f'acco_provider_latency_ms_p95{{provider="{label}"}} '
                f'{float(data["latency_ms_p95"]):.3f}'
            )
    lines.extend(
        [
            "# HELP acco_framework_operations_total SDK/framework operations observed by ACCO.",
            "# TYPE acco_framework_operations_total counter",
        ]
    )
    for key, data in report["frameworks"].items():
        framework, operation = key.split(":", 1)
        f_label = framework.replace("\\", "\\\\").replace('"', '\\"')
        o_label = operation.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(
            "acco_framework_operations_total"
            f'{{framework="{f_label}",operation="{o_label}"}} {data["calls"]}'
        )
        lines.append(
            "acco_framework_context_tokens_removed_total"
            f'{{framework="{f_label}",operation="{o_label}"}} '
            f'{data["estimated_context_tokens_removed"]}'
        )
    return "\n".join(lines) + "\n"
