#!/usr/bin/env python3
"""Prepare frozen ACCO 1.24 end-to-end evidence manifests.

Two lanes are supported:

- regression: re-freeze the published 1.22.1 cohort against ACCO 1.24;
- fresh: freeze a caller-supplied unseen cohort after proving it does not reuse
  task ids from the published cohort.

No agent run is performed here. Freeze first, commit the output, then execute.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from acco.benchmark import (
    MIN_PUBLISHABLE_TASKS,
    MIN_PUBLISHABLE_TRIALS_PER_TASK,
    task_definition_hash,
)


DEFAULT_REFERENCE = Path("benchmarks/e2e-swebench-24-subscription.frozen.json")
DEFAULT_COMMIT = "6c1689d4c88b20077c475e2aa2b15dc414ad50ee"


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: suite must be a JSON object")
    return payload


def _agent_image_arg(runner: dict) -> tuple[list[str], int]:
    command = runner.get("command")
    if not isinstance(command, list):
        raise ValueError("runner.command must be an array")
    try:
        index = command.index("--image") + 1
    except ValueError as exc:
        raise ValueError("runner.command must contain --image") from exc
    if index >= len(command):
        raise ValueError("runner.command --image requires a value")
    return command, index


def _normalize_runner(suite: dict, *, commit: str, image: str) -> None:
    runner = suite.get("runner")
    if not isinstance(runner, dict):
        raise ValueError("suite requires runner object")
    command, image_index = _agent_image_arg(runner)
    command[image_index] = image
    runner["agent_image"] = image
    # claude_docker mounts the task snapshot at /testbed; ACCO's project-scoped
    # state keys hash that child-side path, so evidence collection must use it.
    runner["runtime_state_project_root"] = "/testbed"
    profiles = runner.get("condition_profiles")
    if not isinstance(profiles, dict):
        profiles = {
            "baseline": {"install_acco": False, "label": "claude-code"},
            "enabled": {
                "install_acco": True,
                "instrumentation": "setup",
            },
        }
        runner["condition_profiles"] = profiles
    enabled = profiles.get("enabled")
    if not isinstance(enabled, dict):
        raise ValueError("runner.condition_profiles.enabled must be an object")
    enabled["install_acco"] = True
    enabled["instrumentation"] = "setup"
    enabled["label"] = f"claude-code+acco-{commit[:7]}"


def _freeze(suite: dict, *, scope: str, seed: int) -> dict:
    design = suite.setdefault("design", {})
    design["condition_order_seed"] = int(seed)
    protocol = suite.setdefault("protocol", {})
    protocol.update(
        {
            "task_definitions_frozen": True,
            "condition_order_randomized": True,
            "independent_verification": True,
            "history_isolated": True,
            "hidden_tests_after_agent": True,
            "development_excluded": True,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "evidence_scope": scope,
            "task_definition_sha256": "",
        }
    )
    protocol["task_definition_sha256"] = task_definition_hash(suite)
    return suite


def _validate_broad(suite: dict) -> None:
    tasks = suite.get("tasks")
    if not isinstance(tasks, list) or len(tasks) < MIN_PUBLISHABLE_TASKS:
        raise ValueError(
            f"fresh suite needs at least {MIN_PUBLISHABLE_TASKS} tasks"
        )
    trials = (suite.get("design") or {}).get("trials_per_task")
    if (
        isinstance(trials, bool)
        or not isinstance(trials, int)
        or trials < MIN_PUBLISHABLE_TRIALS_PER_TASK
    ):
        raise ValueError(
            "fresh suite needs at least "
            f"{MIN_PUBLISHABLE_TRIALS_PER_TASK} trials per task"
        )


def _assert_unseen(candidate: dict, reference: dict) -> None:
    old = {
        str(task.get("id"))
        for task in reference.get("tasks", [])
        if isinstance(task, dict)
    }
    new = {
        str(task.get("id"))
        for task in candidate.get("tasks", [])
        if isinstance(task, dict)
    }
    overlap = sorted(old & new)
    if overlap:
        raise ValueError(
            "fresh cohort reuses published task ids: " + ", ".join(overlap)
        )


def _write(path: Path, suite: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    print(f"task_definition_sha256={suite['protocol']['task_definition_sha256']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("regression", "fresh"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    parser.add_argument(
        "--agent-image",
        default=f"acco-e2e-agent:2.1.276-acco-{DEFAULT_COMMIT[:7]}",
    )
    parser.add_argument("--seed", type=int, default=20260930)
    args = parser.parse_args()

    suite = deepcopy(_load(args.source))
    reference = _load(args.reference)
    _normalize_runner(suite, commit=args.commit, image=args.agent_image)

    if args.mode == "fresh":
        _validate_broad(suite)
        _assert_unseen(suite, reference)
        scope = "fresh-unseen-1.24-headline"
    else:
        reference_ids = {
            str(task.get("id"))
            for task in reference.get("tasks", [])
            if isinstance(task, dict)
        }
        source_ids = {
            str(task.get("id"))
            for task in suite.get("tasks", [])
            if isinstance(task, dict)
        }
        if source_ids != reference_ids:
            raise ValueError(
                "regression mode must use exactly the published 1.22.1 task ids"
            )
        scope = "published-cohort-1.24-regression"

    _freeze(suite, scope=scope, seed=args.seed)
    _write(args.output, suite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
