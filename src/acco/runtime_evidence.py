"""Content-free runtime activation evidence for end-to-end experiments."""

from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
from typing import Any

from .cache_ttl import cache_ttl_report
from .efficiency.store import load_events
from .observability import observability_report
from .recovery import RecoveryStore, recovery_path
from .sessions import analyze
from .tool_field_learning import field_learning_report


def collect_runtime_activation(
    root: Path,
    transcript: Path,
    *,
    state_root: Path,
    state_project_root: Path | None = None,
) -> dict[str, Any]:
    """Collect content-free evidence that ACCO runtime mechanisms actually fired."""
    project_root = (state_project_root or root).resolve()
    previous_state = os.environ.get("ACCO_STATE_DIR")
    os.environ["ACCO_STATE_DIR"] = str(state_root)
    try:
        events = load_events(project_root)
        event_kinds = Counter(
            str(event.get("kind") or "unknown")
            for event in events
            if isinstance(event, dict)
        )
        report = analyze([transcript], keep_content=False)
        tool_calls = Counter(
            str(call.name)
            for call in report.calls
            if isinstance(call.name, str)
            and (
                "acco" in call.name.lower()
                or call.name in {"execute", "batch_execute", "recover"}
            )
        )

        recovery = {
            "records": 0,
            "byte_records": 0,
            "object_records": 0,
            "dependencies": 0,
            "used_bytes": 0,
        }
        if recovery_path(project_root).is_file():
            recovery = {
                key: value
                for key, value in RecoveryStore(project_root).stats().items()
                if key != "path"
            }

        fields = field_learning_report(project_root)
        cache = cache_ttl_report(project_root)
        observability = observability_report(project_root, days=3650)

        surface_activity = {
            "recovery_v2": int(recovery.get("records", 0) or 0) > 0,
            "tool_field_learning": bool(fields.get("fields")),
            "cache_ttl_learning": bool(cache.get("estimates"))
            or event_kinds.get("cache_ttl_observation", 0) > 0,
            "output_holdout": (
                event_kinds.get("output_holdout_assignment", 0) > 0
                or event_kinds.get("output_holdout_observation", 0) > 0
            ),
            "provider_observability": bool(observability.get("providers"))
            or bool(observability.get("frameworks")),
            "out_of_context_execution": any(
                name.endswith("execute")
                or name.endswith("execute_file")
                or name.endswith("batch_execute")
                for name in tool_calls
            ),
            "task_contract": any("task_contract" in kind for kind in event_kinds),
            "session_continuity": any(
                token in kind
                for kind in event_kinds
                for token in ("session_", "continuity", "checkpoint", "guardian")
            ),
        }

        return {
            "schema": 1,
            "event_kinds": dict(sorted(event_kinds.items())),
            "acco_tool_calls": dict(sorted(tool_calls.items())),
            "recovery": recovery,
            "tool_fields": fields,
            "cache_ttl": cache,
            "observability": observability,
            "surface_activity": surface_activity,
            "any_activity": bool(events)
            or bool(tool_calls)
            or any(surface_activity.values()),
            "claim_boundary": (
                "Activation counters prove only that a mechanism was exercised. "
                "Task success, quality, and cost effects remain properties of the paired "
                "end-to-end benchmark."
            ),
        }
    finally:
        if previous_state is None:
            os.environ.pop("ACCO_STATE_DIR", None)
        else:
            os.environ["ACCO_STATE_DIR"] = previous_state


def aggregate_runtime_activation(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-run runtime evidence without turning availability into efficacy."""
    enabled = [run for run in runs if run.get("condition") == "enabled"]
    collected = [
        run.get("runtime_activation")
        for run in enabled
        if isinstance(run.get("runtime_activation"), dict)
    ]
    event_kinds: Counter[str] = Counter()
    tool_calls: Counter[str] = Counter()
    surfaces: Counter[str] = Counter()
    runs_with_any = 0
    for item in collected:
        event_kinds.update(
            {
                str(key): int(value)
                for key, value in (item.get("event_kinds") or {}).items()
                if isinstance(value, int) and not isinstance(value, bool)
            }
        )
        tool_calls.update(
            {
                str(key): int(value)
                for key, value in (item.get("acco_tool_calls") or {}).items()
                if isinstance(value, int) and not isinstance(value, bool)
            }
        )
        if item.get("any_activity") is True:
            runs_with_any += 1
        for surface, active in (item.get("surface_activity") or {}).items():
            if active is True:
                surfaces[str(surface)] += 1

    return {
        "schema": 1,
        "enabled_runs": len(enabled),
        "runs_with_activation_evidence": len(collected),
        "runs_with_any_activity": runs_with_any,
        "coverage_complete": len(enabled) > 0 and len(collected) == len(enabled),
        "event_kinds": dict(sorted(event_kinds.items())),
        "acco_tool_calls": dict(sorted(tool_calls.items())),
        "surface_runs": dict(sorted(surfaces.items())),
        "claim_boundary": (
            "This report measures feature activation only. A surface with zero "
            "activation is not covered by the experiment, and an activated surface "
            "does not by itself establish benefit."
        ),
    }
