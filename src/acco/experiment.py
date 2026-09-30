"""Execute reproducible paired baseline/ACCO coding experiments."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import tarfile
from pathlib import Path
from typing import Any

from .benchmark import (
    MIN_PUBLISHABLE_TASKS,
    MIN_PUBLISHABLE_TRIALS_PER_TASK,
    task_definition_hash,
)
from .install import HOOK_COMMAND, install, user_settings_path
from .output_telemetry import load_output_telemetry_from_state
from .session_metrics import efficiency_event_metrics, transcript_session_metrics
from .runtime_evidence import collect_runtime_activation
from .sessions import analyze, transcript_paths

CONDITIONS = ("baseline", "enabled")
# "hooks" installs only the Claude hooks (the frozen protocol); "setup" applies
# the full `acco setup --host claude` configuration a real user gets.
INSTRUMENTATION_MODES = ("hooks", "setup")


def prompt_sha256(prompt: str) -> str:
    """Handle prompt sha256."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _load(path: Path) -> dict:
    """Load the requested value."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("experiment suite must be a JSON object")
    return payload


def _contains_hook(value: Any) -> bool:
    """Handle contains hook."""
    if isinstance(value, dict):
        return any(_contains_hook(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_hook(item) for item in value)
    return isinstance(value, str) and value.strip() == HOOK_COMMAND


def user_acco_hook_configured() -> bool:
    """Return whether the user-level ACCO hook is configured."""
    path = user_settings_path()
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return _contains_hook(payload)


def validate_suite(
    suite_path: Path,
    *,
    require_frozen: bool = True,
    require_broad: bool = True,
) -> dict:
    """Validate suite."""
    suite_path = suite_path.resolve()
    suite = _load(suite_path)

    if suite.get("suite_version") != 1:
        raise ValueError("suite_version must be 1")

    protocol = suite.get("protocol")
    design = suite.get("design")
    repositories = suite.get("repositories")
    tasks = suite.get("tasks")
    runner = suite.get("runner")

    if not isinstance(protocol, dict):
        raise ValueError("suite requires protocol object")
    if not isinstance(design, dict):
        raise ValueError("suite requires design object")
    if not isinstance(repositories, dict) or not repositories:
        raise ValueError("suite requires repositories object")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("suite requires nonempty tasks list")
    if not isinstance(runner, dict):
        raise ValueError("suite requires runner object")

    trials = design.get("trials_per_task")
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        raise ValueError("design.trials_per_task must be a positive integer")
    seed = design.get("condition_order_seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("design.condition_order_seed must be an integer")

    command = runner.get("command")
    if not isinstance(command, list) or not command or not all(
        isinstance(item, str) and item for item in command
    ):
        raise ValueError("runner.command must be a nonempty string array")
    model = str(runner.get("model", "")).strip()
    if not model:
        raise ValueError("runner.model is required")
    mode = runner.get("transcript_mode", "claude-project")
    if mode not in {"claude-project", "path"}:
        raise ValueError("runner.transcript_mode must be claude-project or path")
    profiles = runner.get("condition_profiles")
    if profiles is not None:
        if not isinstance(profiles, dict) or set(profiles) != set(CONDITIONS):
            raise ValueError(
                "runner.condition_profiles must define exactly baseline and enabled"
            )
        for condition in CONDITIONS:
            profile = profiles[condition]
            if not isinstance(profile, dict):
                raise ValueError(
                    f"runner.condition_profiles.{condition} must be an object"
                )
            install_acco = profile.get("install_acco")
            if not isinstance(install_acco, bool):
                raise ValueError(
                    "runner.condition_profiles."
                    + condition
                    + ".install_acco must be boolean"
                )
            instrumentation = profile.get("instrumentation", "hooks")
            if instrumentation not in INSTRUMENTATION_MODES:
                raise ValueError(
                    "runner.condition_profiles."
                    + condition
                    + ".instrumentation must be hooks or setup"
                )
            label = profile.get("label")
            if label is not None and (
                not isinstance(label, str) or not label.strip()
            ):
                raise ValueError(
                    f"runner.condition_profiles.{condition}.label must be nonempty"
                )
            profile_model = profile.get("model")
            if profile_model is not None and (
                not isinstance(profile_model, str) or not profile_model.strip()
            ):
                raise ValueError(
                    f"runner.condition_profiles.{condition}.model must be nonempty"
                )
            profile_env = profile.get("env", {})
            if not isinstance(profile_env, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in profile_env.items()
            ):
                raise ValueError(
                    f"runner.condition_profiles.{condition}.env must be string-to-string"
                )

    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("every task must be an object")
        task_id = str(task.get("id", "")).strip()
        if not task_id or task_id in seen:
            raise ValueError(f"task id missing or duplicated: {task_id!r}")
        seen.add(task_id)
        repo_id = str(task.get("repository", "")).strip()
        if repo_id not in repositories:
            raise ValueError(f"task {task_id}: unknown repository {repo_id!r}")
        repo = repositories[repo_id]
        if not isinstance(repo, dict):
            raise ValueError(f"repository {repo_id}: definition must be an object")
        revision = str(task.get("revision", "")).strip()
        if not revision:
            raise ValueError(f"task {task_id}: revision is required")
        repo_revision = str(repo.get("revision", "")).strip()
        if repo_revision and revision != repo_revision:
            raise ValueError(
                f"task {task_id}: revision must equal repositories.{repo_id}.revision "
                "when the repository pins a single revision"
            )
        prompt = task.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"task {task_id}: prompt is required")
        expected_prompt = str(task.get("prompt_sha256", "")).strip()
        actual_prompt = prompt_sha256(prompt)
        if expected_prompt != actual_prompt:
            raise ValueError(
                f"task {task_id}: prompt_sha256 mismatch; expected {actual_prompt}"
            )
        test_patch = task.get("test_patch")
        if test_patch is not None and (
            not isinstance(test_patch, str) or not test_patch.strip()
        ):
            raise ValueError(f"task {task_id}: test_patch must be a nonempty string")
        verifier = task.get("verifier")
        swebench = task.get("swebench")
        if verifier is None and swebench is None:
            raise ValueError(
                f"task {task_id}: verifier or swebench grader is required"
            )
        if verifier is not None:
            if not isinstance(verifier, list) or not verifier:
                raise ValueError(f"task {task_id}: verifier must contain commands")
            for cmd in verifier:
                if not isinstance(cmd, list) or not cmd or not all(
                    isinstance(arg, str) and arg for arg in cmd
                ):
                    raise ValueError(
                        f"task {task_id}: each verifier command must be a string array"
                    )
        if swebench is not None:
            if not isinstance(swebench, dict):
                raise ValueError(f"task {task_id}: swebench must be an object")
            for field in ("image", "test_command", "env_activate"):
                if not isinstance(swebench.get(field), str) or not swebench[field].strip():
                    raise ValueError(
                        f"task {task_id}: swebench.{field} must be a nonempty string"
                    )
            if not isinstance(test_patch, str) or not test_patch.strip():
                raise ValueError(
                    f"task {task_id}: SWE-bench grading requires test_patch"
                )
            source = task.get("source")
            fail_to_pass = source.get("fail_to_pass") if isinstance(source, dict) else None
            if (
                not isinstance(fail_to_pass, list)
                or not fail_to_pass
                or not all(isinstance(t, str) and t for t in fail_to_pass)
            ):
                raise ValueError(
                    f"task {task_id}: SWE-bench grading requires "
                    "source.fail_to_pass as a nonempty list of test ids"
                )

    if require_broad:
        if len(tasks) < MIN_PUBLISHABLE_TASKS:
            raise ValueError(
                f"broad evidence requires at least {MIN_PUBLISHABLE_TASKS} tasks; "
                f"found {len(tasks)}"
            )
        if trials < MIN_PUBLISHABLE_TRIALS_PER_TASK:
            raise ValueError(
                "broad evidence requires at least "
                f"{MIN_PUBLISHABLE_TRIALS_PER_TASK} trials per task; found {trials}"
            )

    if require_frozen:
        for key in (
            "task_definitions_frozen",
            "condition_order_randomized",
            "independent_verification",
            "history_isolated",
            "hidden_tests_after_agent",
        ):
            if protocol.get(key) is not True:
                raise ValueError(f"protocol.{key} must be true")
        if not str(protocol.get("frozen_at", "")).strip():
            raise ValueError("protocol.frozen_at is required")
        expected = str(protocol.get("task_definition_sha256", "")).strip().lower()
        actual = task_definition_hash(suite)
        if expected != actual:
            raise ValueError(
                "task definition hash mismatch; freeze with "
                f"{actual}"
            )

    return suite


def build_schedule(suite: dict) -> list[dict]:
    """Build schedule."""
    design = suite["design"]
    trials = int(design["trials_per_task"])
    seed = int(design["condition_order_seed"])
    rng = random.Random(seed)

    pairs = [
        {"task": task["id"], "trial": trial}
        for task in suite["tasks"]
        for trial in range(1, trials + 1)
    ]
    rng.shuffle(pairs)

    schedule: list[dict] = []
    for pair in pairs:
        conditions = list(CONDITIONS)
        rng.shuffle(conditions)
        for condition in conditions:
            schedule.append({**pair, "condition": condition})
    return schedule


def _git(source: Path, *args: str, strip: bool = True) -> str:
    """Handle git."""
    proc = subprocess.run(
        ["git", "-C", str(source), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise ValueError(
            f"git {' '.join(args)} failed for {source}: {proc.stderr.strip()}"
        )
    return proc.stdout.strip() if strip else proc.stdout


def _validate_repository(source: Path, revision: str) -> str:
    """Validate repository."""
    if not source.is_dir():
        raise ValueError(f"repository path not found: {source}")
    resolved = _git(source, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if not resolved:
        raise ValueError(f"revision not found in {source}: {revision}")
    return resolved


def _index_entries(listing: str, *, tree: bool) -> dict[str, tuple[str, str]]:
    """Parse NUL-separated ls-tree/ls-files output into path -> (mode, blob)."""
    entries = {}
    for record in filter(None, listing.split("\0")):
        meta, path = record.split("\t", 1)
        fields = meta.split()
        mode, sha = (fields[0], fields[2]) if tree else (fields[0], fields[1])
        entries[path] = (mode, sha)
    return entries


def _restore_archive_attribute_changes(
    source: Path, revision: str, destination: Path
) -> bool:
    """Undo export-subst/export-ignore so the snapshot equals the revision tree."""
    expected = _index_entries(
        _git(source, "ls-tree", "-r", "-z", revision, strip=False), tree=True
    )
    actual = _index_entries(
        _git(destination, "ls-files", "-s", "-z", strip=False), tree=False
    )
    changed = False
    for path, (mode, sha) in expected.items():
        if mode not in {"100644", "100755"} or actual.get(path) == (mode, sha):
            continue
        blob = subprocess.run(
            ["git", "-C", str(source), "cat-file", "blob", sha],
            capture_output=True,
            check=True,
        ).stdout
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        target.chmod(0o755 if mode == "100755" else 0o644)
        changed = True
    return changed


def _export_history_isolated_snapshot(
    source: Path,
    revision: str,
    destination: Path,
) -> None:
    """Export one commit without exposing later Git history to the agent."""
    destination.mkdir(parents=True, exist_ok=False)
    proc = subprocess.Popen(
        ["git", "-C", str(source), "archive", "--format=tar", revision],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            archive.extractall(destination)
    finally:
        proc.stdout.close()
    stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    if proc.stderr:
        proc.stderr.close()
    if proc.wait() != 0:
        raise ValueError(
            f"git archive failed for {source}@{revision}: {stderr.strip()}"
        )

    subprocess.run(["git", "init", "-q", str(destination)], check=True)
    _git(destination, "config", "user.email", "acco-benchmark@example.invalid")
    _git(destination, "config", "user.name", "ACCO Benchmark")
    # --force: the archive holds exactly the revision's tracked files, some of
    # which may match .gitignore (e.g. generated C sources committed upstream).
    _git(destination, "add", "-A", "--force")
    if _restore_archive_attribute_changes(source, revision, destination):
        _git(destination, "add", "-A", "--force")
    proc = subprocess.run(
        [
            "git", "-C", str(destination), "commit", "-q", "--no-gpg-sign",
            "-m", f"benchmark snapshot {revision}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise ValueError(
            f"failed to initialize isolated benchmark snapshot: {proc.stderr.strip()}"
        )


def _changed_paths(worktree: Path) -> set[str]:
    """Return modified, untracked and ignored paths relative to the snapshot."""
    raw = _git(
        worktree, "status", "--porcelain=v1", "-uall", "--ignored", "-z", strip=False
    )
    return {entry[3:] for entry in raw.split("\0") if len(entry) > 3}


def _instrument(worktree: Path, mode: str) -> list[str]:
    """Apply ACCO to a snapshot and return every path the instrumentation touched."""
    before = _changed_paths(worktree)
    if mode == "setup":
        from .integration_setup import setup_integrations

        home = worktree.parent / "setup-home"
        home.mkdir(exist_ok=True)
        setup_integrations(worktree, ("claude",), home=home)
        mcp = worktree / ".mcp.json"
        if mcp.is_file():
            # The agent may run in a container where the worktree has another
            # absolute path; the MCP server is launched from the project root.
            payload = json.loads(mcp.read_text(encoding="utf-8"))
            payload["mcpServers"]["acco"]["args"] = ["serve", "."]
            mcp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        # Stand-in for the one-time interactive approval a real user gives to
        # the project MCP server; headless runs cannot prompt for it.
        local = worktree / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(
            json.dumps({"enableAllProjectMcpServers": True}, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        install(worktree)
    return sorted(_changed_paths(worktree) - before)


def _remove_instrumentation(worktree: Path, paths: list[str]) -> None:
    """Restore instrumented paths to the snapshot so they never reach the patch."""
    tracked = set(_git(worktree, "ls-files", "-z", strip=False).split("\0"))
    for relative in paths:
        target = worktree / relative
        if relative in tracked:
            target.parent.mkdir(parents=True, exist_ok=True)
            _git(worktree, "checkout", "HEAD", "--", relative)
            continue
        target.unlink(missing_ok=True)
        parent = target.parent
        while parent != worktree:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def _condition_profile(runner: dict, condition: str) -> dict:
    """Return one normalized experimental condition profile."""
    profiles = runner.get("condition_profiles")
    if isinstance(profiles, dict):
        raw = profiles[condition]
        install_value = raw.get("install_acco")
        env = dict(raw.get("env", {}))
        return {
            "label": str(raw.get("label") or condition),
            "install_acco": bool(install_value),
            "instrumentation": str(raw.get("instrumentation", "hooks")),
            "env": env,
            "model": (
                str(raw["model"]).strip()
                if isinstance(raw.get("model"), str) and raw["model"].strip()
                else str(runner["model"])
            ),
        }
    return {
        "label": condition,
        "install_acco": condition == "enabled",
        "instrumentation": "hooks",
        "env": {},
        "model": str(runner["model"]),
    }


def _expand_command(
    command: list[str],
    *,
    worktree: Path,
    transcript: Path,
    prompt: str,
    prompt_file: Path,
    model: str,
    condition: str,
    task_image: str = "",
) -> list[str]:
    """Expand command."""
    values = {
        "task_image": task_image,
        "worktree": worktree.as_posix(),
        "transcript": transcript.as_posix(),
        "prompt": prompt,
        "prompt_file": prompt_file.as_posix(),
        "model": model,
        "condition": condition,
    }
    # One pass over each argument: substituted text (e.g. a prompt that itself
    # contains "{model}") is never re-scanned, and unknown braces stay literal.
    placeholder = re.compile(r"\{(" + "|".join(map(re.escape, values)) + r")\}")
    return [
        placeholder.sub(lambda match: values[match.group(1)], item)
        for item in command
    ]


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout: int,
) -> tuple[int, float]:
    """Run command."""
    start = time.monotonic()
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            proc = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return 124, time.monotonic() - start
    return proc.returncode, time.monotonic() - start


def _checkpoint(path: Path, payload: dict) -> None:
    """Handle checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _existing_keys(output_path: Path, suite: dict) -> tuple[dict, set[tuple[str, str, str]]]:
    """Handle existing keys."""
    if not output_path.is_file():
        payload = {
            "suite_version": suite["suite_version"],
            "protocol": suite["protocol"],
            "design": suite["design"],
            "repositories": suite["repositories"],
            "runner": suite["runner"],
            "tasks": suite["tasks"],
            "runs": [],
        }
        for optional in ("quality_grader", "evidence"):
            if optional in suite:
                payload[optional] = suite[optional]
        return payload, set()

    payload = _load(output_path)
    for key in (
        "suite_version",
        "protocol",
        "design",
        "repositories",
        "runner",
        "tasks",
        "quality_grader",
        "evidence",
    ):
        if payload.get(key) != suite.get(key):
            raise ValueError(
                f"existing result {output_path} does not match suite field {key}"
            )
    keys = {
        (
            str(run.get("task", "")),
            str(run.get("trial", "")),
            str(run.get("condition", "")),
        )
        for run in payload.get("runs", [])
        if isinstance(run, dict)
    }
    return payload, keys


def _swebench_reference_passed(task: dict, ref_dir: Path, *, timeout: int) -> set[str]:
    """Tests passing on the unpatched code with the hidden tests applied.

    Computed once per task and cached, so regressions are judged against what
    the image itself can pass rather than the exit code of the whole command.
    """
    from .swebench_docker import parse_test_statuses, passed_tests, verify_swebench

    swebench = task["swebench"]
    out = ref_dir / "swebench.stdout"
    if not out.is_file():
        ref_dir.mkdir(parents=True, exist_ok=True)
        empty = ref_dir / "empty.patch"
        empty.write_text("", encoding="utf-8")
        test_patch = ref_dir / "hidden-test.patch"
        test_patch.write_text(task["test_patch"], encoding="utf-8")
        rc, _ = verify_swebench(
            image=swebench["image"],
            agent_patch=empty,
            test_patch=test_patch,
            test_command=swebench["test_command"],
            env_activate=swebench["env_activate"],
            stdout_path=out,
            stderr_path=ref_dir / "swebench.stderr",
            timeout=timeout,
        )
        if rc == 124:
            out.unlink(missing_ok=True)
            raise ValueError(f"task {task['id']}: reference verification timed out")
    text = out.read_text(encoding="utf-8", errors="replace")
    if not parse_test_statuses(text):
        out.unlink(missing_ok=True)
        raise ValueError(
            f"task {task['id']}: reference run produced no test results; "
            "check the image and test command"
        )
    return passed_tests(text)


def _transcript_usage(path: Path) -> dict:
    """Return exact transcript usage totals in experiment-friendly fields."""
    report = analyze([path], keep_content=False)
    usage = report.usage
    fresh = int(usage["input_tokens"])
    cache_created = int(usage["cache_creation_input_tokens"])
    cache_created_5m = sum(int(turn.cache_5m) for turn in report.turns)
    cache_created_1h = sum(int(turn.cache_1h) for turn in report.turns)
    cache_created_unknown = max(
        0, cache_created - cache_created_5m - cache_created_1h
    )
    cache_read = int(usage["cache_read_input_tokens"])
    output = int(usage["output_tokens"])
    return {
        "fresh_input_tokens": fresh,
        "cache_creation_input_tokens": cache_created,
        "cache_creation_5m_input_tokens": cache_created_5m,
        "cache_creation_1h_input_tokens": cache_created_1h,
        "cache_creation_unknown_input_tokens": cache_created_unknown,
        "cache_read_input_tokens": cache_read,
        "input_tokens": fresh + cache_created + cache_read,
        "cached_input_tokens": cache_read,
        "output_tokens": output,
        "model_calls": len(report.turns),
        "tool_calls": len(report.calls),
        "actual_models": sorted(
            {
                str(turn.model)
                for turn in report.turns
                if isinstance(turn.model, str)
                and turn.model
                and turn.model != "unknown"
            }
        ),
    }


def _policy_telemetry(
    state_root: Path,
    *,
    task: str,
    trial: int,
    condition: str,
    transcript_usage: dict,
) -> dict | None:
    """Summarize benchmark-tagged output-policy telemetry for one run."""
    records = []
    for record in load_output_telemetry_from_state(state_root):
        experiment = record.get("experiment")
        if not isinstance(experiment, dict):
            continue
        if (
            str(experiment.get("task") or "") == task
            and str(experiment.get("trial") or "") == str(trial)
            and str(experiment.get("condition") or "") == condition
        ):
            records.append(record)
    if not records:
        return None

    measured = [record for record in records if record.get("usage_available") is True]
    tasks = sorted(
        {
            str(record["task"])
            for record in records
            if isinstance(record.get("task"), str) and record.get("task")
        }
    )
    modes = sorted(
        {
            str(record["mode"])
            for record in records
            if isinstance(record.get("mode"), str) and record.get("mode")
        }
    )
    budgets = [
        int(record["selected_budget"])
        for record in records
        if isinstance(record.get("selected_budget"), int)
        and not isinstance(record.get("selected_budget"), bool)
        and record["selected_budget"] > 0
    ]
    telemetry_usage = {
        field: sum(int(record.get(field, 0)) for record in measured)
        for field in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_creation_5m_input_tokens",
            "cache_creation_1h_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
            "model_calls",
        )
    }
    expected_usage = {
        "input_tokens": transcript_usage["fresh_input_tokens"],
        "cache_creation_input_tokens": transcript_usage["cache_creation_input_tokens"],
        "cache_creation_5m_input_tokens": transcript_usage[
            "cache_creation_5m_input_tokens"
        ],
        "cache_creation_1h_input_tokens": transcript_usage[
            "cache_creation_1h_input_tokens"
        ],
        "cache_read_input_tokens": transcript_usage["cache_read_input_tokens"],
        "output_tokens": transcript_usage["output_tokens"],
        "model_calls": transcript_usage["model_calls"],
    }
    utilizations = [
        float(record["budget_utilization"])
        for record in records
        if isinstance(record.get("budget_utilization"), (int, float))
        and not isinstance(record.get("budget_utilization"), bool)
    ]
    targets = [
        bool(record["target_met"])
        for record in records
        if isinstance(record.get("target_met"), bool)
    ]
    return {
        "records": len(records),
        "measured_records": len(measured),
        "output_task": tasks[0] if len(tasks) == 1 else None,
        "output_mode": modes[0] if len(modes) == 1 else None,
        "policy_budget": budgets[0] if budgets and len(set(budgets)) == 1 else None,
        "selected_budgets": sorted(set(budgets)),
        "mean_budget_utilization": (
            sum(utilizations) / len(utilizations) if utilizations else None
        ),
        "target_met_rate": (
            sum(targets) / len(targets) if targets else None
        ),
        "usage_matches_transcript": telemetry_usage == expected_usage,
        "telemetry_usage": telemetry_usage,
    }


def run_experiment(
    suite_path: Path,
    output_path: Path,
    *,
    dry_run: bool = False,
    allow_development: bool = False,
    allow_user_hook: bool = False,
    only_tasks: set[str] | None = None,
) -> dict:
    """Run experiment."""
    suite_path = suite_path.resolve()
    output_path = output_path.resolve()
    suite = validate_suite(
        suite_path,
        require_frozen=not allow_development,
        require_broad=not allow_development,
    )
    all_task_ids = {str(task["id"]) for task in suite["tasks"]}
    selected_ids = set(only_tasks or all_task_ids)
    unknown = sorted(selected_ids - all_task_ids)
    if unknown:
        raise ValueError("unknown experiment task(s): " + ", ".join(unknown))
    if not selected_ids:
        raise ValueError("at least one experiment task must be selected")
    selected_tasks = [
        task for task in suite["tasks"] if str(task["id"]) in selected_ids
    ]
    schedule = [
        item for item in build_schedule(suite) if item["task"] in selected_ids
    ]

    if dry_run:
        return {
            "task_count": len(selected_tasks),
            "trials_per_task": suite["design"]["trials_per_task"],
            "paired_trials": len(schedule) // 2,
            "run_count": len(schedule),
            "schedule": schedule,
            "condition_profiles": {
                condition: _condition_profile(suite["runner"], condition)
                for condition in CONDITIONS
            },
            "task_definition_sha256": task_definition_hash(suite),
        }

    if user_acco_hook_configured() and not allow_user_hook:
        raise ValueError(
            "user-level 'acco hook' is configured. Remove/disable it for "
            "the experiment so benchmark condition profiles are not instrumented twice."
        )

    base_dir = suite_path.parent
    selected_repo_ids = {str(task["repository"]) for task in selected_tasks}
    repositories: dict[str, Path] = {}
    for repo_id in selected_repo_ids:
        definition = suite["repositories"][repo_id]
        source = (base_dir / str(definition["path"])).resolve()
        if not source.is_dir():
            raise ValueError(f"repository path not found: {source}")
        repositories[repo_id] = source

    resolved_revisions: dict[tuple[str, str], str] = {}
    for task in selected_tasks:
        repo_id = str(task["repository"])
        revision = str(task["revision"]).strip()
        key = (repo_id, revision)
        if key not in resolved_revisions:
            resolved_revisions[key] = _validate_repository(
                repositories[repo_id],
                revision,
            )

    result, completed = _existing_keys(output_path, suite)
    tasks = {task["id"]: task for task in selected_tasks}
    runner = suite["runner"]
    timeout = int(runner.get("timeout_seconds", 1800))
    if timeout < 1:
        raise ValueError("runner.timeout_seconds must be positive")
    extra_env = runner.get("env", {})
    if not isinstance(extra_env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in extra_env.items()
    ):
        raise ValueError("runner.env must be a string-to-string object")

    artifacts = output_path.parent / (output_path.stem + ".artifacts")

    for sequence, item in enumerate(schedule, start=1):
        key = (item["task"], str(item["trial"]), item["condition"])
        if key in completed:
            continue

        task = tasks[item["task"]]
        source = repositories[task["repository"]]
        revision = resolved_revisions[(task["repository"], str(task["revision"]).strip())]
        run_dir = artifacts / item["task"] / f"trial-{item['trial']}" / item["condition"]
        run_dir.mkdir(parents=True, exist_ok=True)
        transcript = run_dir / "transcript.jsonl"
        prompt_file = run_dir / "prompt.txt"
        prompt_file.write_text(task["prompt"], encoding="utf-8")
        stdout_path = run_dir / "agent.stdout"
        stderr_path = run_dir / "agent.stderr"

        with tempfile.TemporaryDirectory(prefix="acco-e2e-") as tmp:
            worktree = Path(tmp) / "repo"
            _export_history_isolated_snapshot(source, revision, worktree)
            try:
                for setup in task.get("setup", []):
                    setup_proc = subprocess.run(
                        setup,
                        cwd=worktree,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    if setup_proc.returncode:
                        raise ValueError(
                            f"task {task['id']}: setup failed: {' '.join(setup)}\n"
                            + setup_proc.stderr[-2000:]
                        )

                env = os.environ.copy()
                env.update(extra_env)
                env["ACCO_BENCHMARK_CONDITION"] = item["condition"]
                env["ACCO_BENCHMARK_TASK"] = task["id"]
                env["ACCO_BENCHMARK_TRIAL"] = str(item["trial"])
                run_state_dir = run_dir / "acco-state"
                env["ACCO_STATE_DIR"] = str(run_state_dir)
                profile = _condition_profile(runner, item["condition"])
                env.update(profile["env"])
                instrumented = profile["install_acco"]
                run_model = profile["model"]
                instrumentation_paths: list[str] = []
                if instrumented:
                    env.pop("ACCO_DISABLED", None)
                    instrumentation_paths = _instrument(
                        worktree, profile["instrumentation"]
                    )
                else:
                    env["ACCO_DISABLED"] = "1"

                before = set(transcript_paths(worktree))
                command = _expand_command(
                    runner["command"],
                    worktree=worktree,
                    transcript=transcript,
                    prompt=task["prompt"],
                    prompt_file=prompt_file,
                    model=run_model,
                    condition=item["condition"],
                    task_image=str((task.get("swebench") or {}).get("image", "")),
                )
                agent_rc, seconds = _run_command(
                    command,
                    cwd=worktree,
                    env=env,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    timeout=timeout,
                )
                if agent_rc != 0:
                    stdout_tail = stdout_path.read_text(
                        encoding="utf-8", errors="replace"
                    )[-2000:]
                    stderr_tail = stderr_path.read_text(
                        encoding="utf-8", errors="replace"
                    )[-2000:]
                    raise ValueError(
                        f"task {task['id']} trial {item['trial']} "
                        f"{item['condition']}: agent runner exited {agent_rc}\n"
                        f"stdout tail:\n{stdout_tail}\n"
                        f"stderr tail:\n{stderr_tail}"
                    )

                mode = runner.get("transcript_mode", "claude-project")
                if mode == "claude-project":
                    after = set(transcript_paths(worktree))
                    created = sorted(after - before)
                    if len(created) != 1:
                        raise ValueError(
                            f"task {task['id']} trial {item['trial']} "
                            f"{item['condition']}: expected exactly one new Claude "
                            f"transcript, found {len(created)}"
                        )
                    shutil.copyfile(created[0], transcript)
                elif not transcript.is_file():
                    raise ValueError(
                        f"runner did not create transcript: {transcript}"
                    )

                usage = _transcript_usage(transcript)
                session_metrics = transcript_session_metrics(transcript)
                efficiency_telemetry = efficiency_event_metrics(run_state_dir)
                policy_telemetry = (
                    _policy_telemetry(
                        run_state_dir,
                        task=str(task["id"]),
                        trial=int(item["trial"]),
                        condition=str(item["condition"]),
                        transcript_usage=usage,
                    )
                    if instrumented
                    else None
                )
                runtime_activation = (
                    collect_runtime_activation(
                        worktree,
                        transcript,
                        state_root=run_state_dir,
                        state_project_root=(
                            Path(str(runner["runtime_state_project_root"]))
                            if runner.get("runtime_state_project_root")
                            else None
                        ),
                    )
                    if instrumented
                    else None
                )

                # Remove benchmark instrumentation before capturing the solution.
                # Hooks, settings, lock files, MCP config and skills written for
                # the enabled arm are not part of the agent's solution and must
                # never be sent to the independent grader.
                if instrumented:
                    _remove_instrumentation(worktree, instrumentation_paths)

                # Stage the complete working tree so new/deleted files are included
                # in the patch as well as modifications to tracked files.
                _git(worktree, "add", "-A")
                agent_patch = run_dir / "agent.patch"
                agent_patch.write_text(
                    # strip=False: a patch without its final newline is "corrupt"
                    _git(worktree, "diff", "--cached", "--binary", strip=False),
                    encoding="utf-8",
                )

                verification = []
                verifier_ok = True
                test_patch = task.get("test_patch")
                swebench = task.get("swebench")
                if swebench is not None:
                    from .swebench_docker import (
                        grade_swebench,
                        passed_tests,
                        strip_test_file_changes,
                        verify_swebench,
                    )

                    verifier_timeout = int(task.get("verifier_timeout_seconds", timeout))
                    test_patch_path = run_dir / "hidden-test.patch"
                    test_patch_path.write_text(test_patch, encoding="utf-8")
                    graded_patch = run_dir / "agent.graded.patch"
                    graded_patch.write_text(
                        strip_test_file_changes(
                            agent_patch.read_text(encoding="utf-8"), test_patch
                        ),
                        encoding="utf-8",
                    )
                    reference_passed = _swebench_reference_passed(
                        task,
                        artifacts / "_reference" / item["task"],
                        timeout=verifier_timeout,
                    )
                    verify_out = run_dir / "swebench.stdout"
                    verify_err = run_dir / "swebench.stderr"
                    rc, elapsed = verify_swebench(
                        image=swebench["image"],
                        agent_patch=graded_patch,
                        test_patch=test_patch_path,
                        test_command=swebench["test_command"],
                        env_activate=swebench["env_activate"],
                        stdout_path=verify_out,
                        stderr_path=verify_err,
                        timeout=verifier_timeout,
                    )
                    grade = grade_swebench(
                        task["source"]["fail_to_pass"],
                        reference_passed,
                        passed_tests(verify_out.read_text(encoding="utf-8", errors="replace")),
                    )
                    verification.append({
                        "kind": "swebench_docker",
                        "image": swebench["image"],
                        "test_command": swebench["test_command"],
                        "exit_code": rc,
                        "seconds": elapsed,
                        "graded_patch": str(graded_patch.relative_to(output_path.parent)),
                        "grade": grade,
                        "stdout": str(verify_out.relative_to(output_path.parent)),
                        "stderr": str(verify_err.relative_to(output_path.parent)),
                    })
                    verifier_ok = grade["resolved"] and rc != 124
                else:
                    if test_patch:
                        patch_stdout = run_dir / "test-patch.stdout"
                        patch_stderr = run_dir / "test-patch.stderr"
                        start = time.monotonic()
                        with patch_stdout.open("wb") as stdout, patch_stderr.open("wb") as stderr:
                            patch_proc = subprocess.run(
                                ["git", "apply", "--whitespace=nowarn", "-"],
                                cwd=worktree,
                                env=env,
                                input=test_patch.encode("utf-8"),
                                stdout=stdout,
                                stderr=stderr,
                                check=False,
                            )
                        verification.append({
                            "kind": "hidden_test_patch",
                            "exit_code": patch_proc.returncode,
                            "seconds": time.monotonic() - start,
                            "stdout": str(patch_stdout.relative_to(output_path.parent)),
                            "stderr": str(patch_stderr.relative_to(output_path.parent)),
                        })
                        verifier_ok = patch_proc.returncode == 0

                    for index, verifier in enumerate(task["verifier"], start=1):
                        verify_out = run_dir / f"verify-{index}.stdout"
                        verify_err = run_dir / f"verify-{index}.stderr"
                        verify_env = env.copy()
                        verify_env["ACCO_DISABLED"] = "1"
                        rc, elapsed = _run_command(
                            verifier,
                            cwd=worktree,
                            env=verify_env,
                            stdout_path=verify_out,
                            stderr_path=verify_err,
                            timeout=int(task.get("verifier_timeout_seconds", timeout)),
                        )
                        verification.append(
                            {
                                "command": verifier,
                                "exit_code": rc,
                                "seconds": elapsed,
                                "stdout": str(verify_out.relative_to(output_path.parent)),
                                "stderr": str(verify_err.relative_to(output_path.parent)),
                            }
                        )
                        verifier_ok = verifier_ok and rc == 0

                success = agent_rc == 0 and verifier_ok
                validation = (
                    "independent verifier passed"
                    if success
                    else "independent verifier failed or agent exited nonzero"
                )
                run = {
                    "task": task["id"],
                    "trial": item["trial"],
                    "condition": item["condition"],
                    "condition_label": profile["label"],
                    "sequence": sequence,
                    "revision": task["revision"],
                    "model": run_model,
                    "prompt_sha256": task["prompt_sha256"],
                    "success": success,
                    "validation": validation,
                    "manual_intervention": False,
                    "seconds": seconds,
                    **usage,
                    "output_task": (
                        policy_telemetry["output_task"] if policy_telemetry else None
                    ),
                    "output_mode": (
                        policy_telemetry["output_mode"] if policy_telemetry else None
                    ),
                    "policy_budget": (
                        policy_telemetry["policy_budget"] if policy_telemetry else None
                    ),
                    "output_policy_telemetry": policy_telemetry,
                    "session_metrics": session_metrics,
                    "session_efficiency_telemetry": efficiency_telemetry,
                    "runtime_activation": runtime_activation,
                    "agent_exit_code": agent_rc,
                    "verification": verification,
                    "agent_patch": str(agent_patch.relative_to(output_path.parent)),
                    "transcripts": [
                        str(transcript.relative_to(output_path.parent))
                    ],
                }
                result["runs"].append(run)
                _checkpoint(output_path, result)
                completed.add(key)
            finally:
                pass

    return result
