"""Paired end-to-end task evaluation from real agent transcripts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from .cost_report import Run, compare_costs
from .pricing import cost, load_rates
from .runtime_evidence import aggregate_runtime_activation
from .sessions import analyze

MIN_PUBLISHABLE_TASKS = 20
MIN_PUBLISHABLE_TRIALS_PER_TASK = 3
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def task_definition_hash(manifest: dict) -> str:
    """Stable hash for task definitions and experimental design.

    Runtime paths, transcripts and outcomes are intentionally excluded so the
    suite can be frozen before any paid agent run.
    """
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("publishable benchmark manifest requires nonempty tasks")
    if not all(isinstance(task, dict) for task in tasks):
        raise ValueError("every task definition must be an object")
    repositories = manifest.get("repositories", {})
    if repositories is None:
        repositories = {}
    if not isinstance(repositories, dict):
        raise ValueError("repositories must be an object when present")
    frozen_repositories = {}
    for repo_id, definition in sorted(repositories.items()):
        if not isinstance(definition, dict):
            raise ValueError(f"repository {repo_id}: definition must be an object")
        frozen_repositories[repo_id] = {
            key: value
            for key, value in sorted(definition.items())
            if key != "path"
        }
    runner = manifest.get("runner", {})
    if not isinstance(runner, dict):
        raise ValueError("runner must be an object")
    normalized = {
        "suite_version": manifest.get("suite_version", 1),
        "design": manifest.get("design", {}),
        "repositories": frozen_repositories,
        "runner": runner,
        "tasks": sorted(tasks, key=lambda task: str(task.get("id", ""))),
    }
    raw = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _publishability_issues(manifest: dict, runs: list[dict]) -> list[str]:
    """Handle publishability issues."""
    issues: list[str] = []
    protocol = manifest.get("protocol")
    tasks = manifest.get("tasks")

    if not isinstance(protocol, dict):
        return ["missing protocol object"]
    if protocol.get("task_definitions_frozen") is not True:
        issues.append("protocol.task_definitions_frozen must be true")
    if protocol.get("condition_order_randomized") is not True:
        issues.append("protocol.condition_order_randomized must be true")
    if protocol.get("independent_verification") is not True:
        issues.append("protocol.independent_verification must be true")
    if protocol.get("history_isolated") is not True:
        issues.append("protocol.history_isolated must be true")
    if protocol.get("hidden_tests_after_agent") is not True:
        issues.append("protocol.hidden_tests_after_agent must be true")
    if not str(protocol.get("frozen_at", "")).strip():
        issues.append("protocol.frozen_at is required")

    expected_hash = str(protocol.get("task_definition_sha256", "")).strip().lower()
    if not _SHA256.fullmatch(expected_hash):
        issues.append("protocol.task_definition_sha256 must be a 64-character SHA-256")
    else:
        try:
            actual_hash = task_definition_hash(manifest)
        except ValueError as exc:
            issues.append(str(exc))
        else:
            if actual_hash != expected_hash:
                issues.append(
                    "task definition hash mismatch: "
                    f"expected {expected_hash}, computed {actual_hash}"
                )

    if not isinstance(tasks, list) or not tasks:
        issues.append("nonempty top-level tasks list is required")
        return issues

    task_defs: dict[str, dict] = {}
    for task in tasks:
        if not isinstance(task, dict):
            issues.append("every task definition must be an object")
            continue
        task_id = str(task.get("id", "")).strip()
        if not task_id:
            issues.append("every task definition requires id")
            continue
        if task_id in task_defs:
            issues.append(f"duplicate task definition: {task_id}")
            continue
        task_defs[task_id] = task
        for field in ("repository", "revision", "prompt_sha256"):
            if not task.get(field):
                issues.append(f"task {task_id}: missing {field}")
        if not task.get("verifier") and not task.get("swebench"):
            issues.append(
                f"task {task_id}: missing independent verifier or SWE-bench grader"
            )

    if len(task_defs) < MIN_PUBLISHABLE_TASKS:
        issues.append(
            f"need at least {MIN_PUBLISHABLE_TASKS} distinct tasks; found {len(task_defs)}"
        )

    trials: dict[str, set[str]] = {task_id: set() for task_id in task_defs}
    models: set[str] = set()
    for run in runs:
        task_id = str(run.get("task", "")).strip()
        if task_id not in task_defs:
            issues.append(f"run references undefined task: {task_id or '<empty>'}")
            continue
        definition = task_defs[task_id]
        if str(run.get("revision", "")).strip() != str(definition.get("revision", "")).strip():
            issues.append(f"task {task_id}: run revision differs from frozen definition")
        if str(run.get("prompt_sha256", "")).strip() != str(
            definition.get("prompt_sha256", "")
        ).strip():
            issues.append(f"task {task_id}: run prompt hash differs from frozen definition")
        if run.get("manual_intervention") not in (None, False):
            issues.append(f"task {task_id}: manual intervention is not publishable")
        trial = str(run.get("trial", "")).strip()
        if trial:
            trials[task_id].add(trial)
        models.add(str(run.get("model", "")).strip())

    for task_id, values in trials.items():
        if len(values) < MIN_PUBLISHABLE_TRIALS_PER_TASK:
            issues.append(
                f"task {task_id}: need at least {MIN_PUBLISHABLE_TRIALS_PER_TASK} "
                f"paired trials; found {len(values)}"
            )

    models.discard("")
    if len(models) != 1:
        issues.append(
            "publishable aggregate requires one exact model id across all runs; "
            f"found {sorted(models)}"
        )

    return list(dict.fromkeys(issues))


def evaluate(
    manifest_path,
    rates_path,
    *,
    require_publishable: bool = False,
) -> dict:
    """Evaluate the requested value."""
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    runs = manifest.get("runs", [])
    if not runs:
        raise ValueError("manifest requires nonempty runs")
    if not all(isinstance(run, dict) for run in runs):
        raise ValueError("every run must be an object")

    rates = load_rates(rates_path)
    seen = set()
    used_paths = set()
    pairs = {}
    trial_counts: Counter[str] = Counter()
    results = {
        arm: {
            "runs": 0,
            "successes": 0,
            "usd": 0.0,
            "seconds": 0.0,
            "input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 0,
            "tool_results": 0,
            "model_calls": 0,
            "repeated_reads": 0,
        }
        for arm in ("baseline", "enabled")
    }
    comparison_runs: dict[str, list[Run]] = {"baseline": [], "enabled": []}

    for run in runs:
        arm = run["condition"]
        if arm not in results:
            raise ValueError("condition must be baseline or enabled")
        if not isinstance(run.get("success"), bool):
            raise ValueError("success must be independently evaluated boolean")
        seconds = run.get("seconds")
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("seconds must be a nonnegative finite number")
        if not run.get("validation"):
            raise ValueError("validation must describe the independent task checks")

        task_id = str(run["task"]).strip()
        trial = str(run["trial"]).strip()
        if not task_id or not trial:
            raise ValueError("task and trial are required")
        key = (task_id, trial)
        if (key, arm) in seen:
            raise ValueError("duplicate task/trial/condition")
        seen.add((key, arm))
        trial_counts[task_id] += 1

        metadata = (run["revision"], run["model"], run["prompt_sha256"])
        if key in pairs and pairs[key] != metadata:
            raise ValueError("paired runs must share revision, model and prompt")
        pairs[key] = metadata

        paths = [(path.parent / p).resolve() for p in run["transcripts"]]
        if not paths or any(not p.is_file() for p in paths):
            raise ValueError("missing transcript")
        if len(set(paths)) != len(paths):
            raise ValueError("duplicate transcript in a run")
        if used_paths.intersection(paths):
            raise ValueError("transcripts must be independent across runs")
        used_paths.update(paths)

        report = analyze(paths)
        if not report.turns:
            raise ValueError("transcripts contain no measured usage")
        if any(t.model != run["model"] for t in report.turns):
            raise ValueError("transcript model differs from run model")
        bill = cost(report, rates)
        if bill["usd"] is None:
            raise ValueError(
                "incomplete cost: " + "; ".join(bill["incomplete_reasons"])
            )

        result = results[arm]
        result["runs"] += 1
        result["successes"] += int(run["success"])
        result["usd"] += bill["usd"]
        result["seconds"] += seconds
        result["tool_results"] += len(report.calls)
        result["model_calls"] += len(report.turns)
        result["repeated_reads"] += sum(n - 1 for _, n, _ in report.duplicate_reads())
        for field in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        ):
            result[field] += report.usage[field]

        # For descriptive total-token comparison, all input categories count as
        # context consumed. Exact USD cost still comes from the provider-aware
        # rate model above, so cache creation/read pricing is not flattened.
        total_input = (
            report.usage["input_tokens"]
            + report.usage["cache_creation_input_tokens"]
            + report.usage["cache_read_input_tokens"]
        )
        comparison_runs[arm].append(
            Run(
                task_id=task_id,
                trial=trial,
                success=run["success"],
                input_tokens=total_input,
                cached_input_tokens=report.usage["cache_read_input_tokens"],
                output_tokens=report.usage["output_tokens"],
                tool_calls=len(report.calls),
                model_calls=len(report.turns),
                latency_ms=float(seconds) * 1000.0,
                cost_usd=float(bill["usd"]),
            )
        )

    if any((key, arm) not in seen for key in pairs for arm in results):
        raise ValueError("every task/trial needs both conditions")

    for result in results.values():
        result["success_rate"] = result["successes"] / result["runs"]
        result["usd_per_success"] = (
            result["usd"] / result["successes"] if result["successes"] else None
        )

    comparison = compare_costs(
        comparison_runs["baseline"],
        comparison_runs["enabled"],
        require_same_tasks=True,
    )
    baseline, enabled = results["baseline"], results["enabled"]
    comparable = (
        enabled["success_rate"] >= baseline["success_rate"]
        and baseline["usd_per_success"]
        and enabled["usd_per_success"] is not None
    )
    savings = (
        100 * (1 - enabled["usd_per_success"] / baseline["usd_per_success"])
        if comparable
        else None
    )

    protocol_issues = _publishability_issues(manifest, runs)
    if require_publishable and protocol_issues:
        raise ValueError(
            "benchmark is not publishable evidence: " + "; ".join(protocol_issues)
        )

    cps_interval = comparison["confidence"]["intervals"].get(
        "cost_per_success_reduction"
    )
    statistically_supported = bool(
        cps_interval is not None and cps_interval[0] > 0
    )
    return {
        "paired_trials": len(pairs),
        "unique_tasks": comparison["unique_task_count"],
        "results": results,
        "cost_per_success_reduction_percent": savings,
        "comparison": comparison,
        "evidence": {
            "protocol_valid": not protocol_issues,
            "protocol_issues": protocol_issues,
            "claim_allowed": not protocol_issues and comparable,
            "statistically_supported_cost_per_success_reduction": statistically_supported,
            "minimum_publishable_tasks": MIN_PUBLISHABLE_TASKS,
            "minimum_publishable_trials_per_task": MIN_PUBLISHABLE_TRIALS_PER_TASK,
            "runtime_activation": aggregate_runtime_activation(runs),
        },
        "note": (
            "Costs come from measured transcripts and include failed runs. "
            "Confidence intervals use a task-cluster bootstrap so repeated trials "
            "do not masquerade as independent tasks."
        ),
    }
