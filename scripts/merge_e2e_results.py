#!/usr/bin/env python3
"""Merge sharded frozen experiment results into one publishable manifest."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from acco.experiment import build_schedule, validate_suite


META_KEYS = (
    "suite_version",
    "protocol",
    "design",
    "repositories",
    "runner",
    "tasks",
    "quality_grader",
    "evidence",
)

# Verification entries that point at run artifacts.
VERIFICATION_PATH_KEYS = ("graded_patch", "stdout", "stderr")


def _rebase(value: str, source: Path, target: Path) -> str:
    """Re-express a path relative to ``source`` as relative to ``target``."""
    if Path(value).is_absolute():
        return value
    return Path(os.path.relpath(source / value, target)).as_posix()


def _rebase_run(run: dict, source: Path, target: Path) -> dict:
    """Keep a run's artifact paths valid once written next to ``target``.

    Shards store artifact paths relative to the shard file, and ``acco
    benchmark`` resolves them relative to the merged manifest.
    """
    run = dict(run)
    transcripts = run.get("transcripts")
    if isinstance(transcripts, list):
        run["transcripts"] = [
            _rebase(p, source, target) if isinstance(p, str) else p
            for p in transcripts
        ]
    if isinstance(run.get("agent_patch"), str):
        run["agent_patch"] = _rebase(run["agent_patch"], source, target)
    verification = run.get("verification")
    if isinstance(verification, list):
        rebased = []
        for item in verification:
            if isinstance(item, dict):
                item = dict(item)
                for key in VERIFICATION_PATH_KEYS:
                    if isinstance(item.get(key), str):
                        item[key] = _rebase(item[key], source, target)
            rebased.append(item)
        run["verification"] = rebased
    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite")
    parser.add_argument("output")
    parser.add_argument("shards", nargs="+")
    args = parser.parse_args()

    suite_path = Path(args.suite).resolve()
    suite = validate_suite(suite_path, require_frozen=True, require_broad=True)
    output = Path(args.output).resolve()

    merged = {key: suite[key] for key in META_KEYS if key in suite}
    merged["runs"] = []
    seen: set[tuple[str, str, str]] = set()

    for raw in args.shards:
        path = Path(raw).resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit(f"{path}: shard must be a JSON object")
        for key in META_KEYS:
            if payload.get(key) != suite.get(key):
                raise SystemExit(f"{path}: frozen metadata differs at {key}")
        for run in payload.get("runs", []):
            if not isinstance(run, dict):
                raise SystemExit(f"{path}: run must be an object")
            key = (
                str(run.get("task", "")),
                str(run.get("trial", "")),
                str(run.get("condition", "")),
            )
            if key in seen:
                raise SystemExit(f"duplicate run across shards: {key}")
            seen.add(key)
            merged["runs"].append(_rebase_run(run, path.parent, output.parent))

    expected = {
        (str(item["task"]), str(item["trial"]), str(item["condition"]))
        for item in build_schedule(suite)
    }
    missing = sorted(expected - seen)
    extra = sorted(seen - expected)
    if missing or extra:
        raise SystemExit(
            f"incomplete shard set: missing={missing[:10]} extra={extra[:10]} "
            f"(expected {len(expected)}, found {len(seen)})"
        )

    merged["runs"].sort(
        key=lambda run: (
            str(run["task"]),
            int(run["trial"]),
            str(run["condition"]),
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(f"merged {len(merged['runs'])} runs -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
