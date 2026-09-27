"""Run an ACCO experiment suite task by task, surviving subscription limits.

Each task is an independent, resumable `acco experiment` (completed runs are
skipped on rerun). Failed attempts are classified from their own log:

  limit  - usage/rate limit: every worker pauses until the reset time when the
           message gives one, else backs off 10 -> 20 -> 30 minutes.
  auth   - expired/invalid token: wait and re-read the token each attempt
           (~/.acco-bench-token, then the host Claude Code login).
  other  - retried twice, then the task is marked failed and skipped.

Usage:
  python scripts/run_resilient_experiment.py SUITE OUT_DIR [--jobs N] [--task ID ...]

Touch <out>/STOP to finish current runs and start no new ones.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
LIMIT = re.compile(
    r"usage limit|limit reached|hit your limit|rate.?limit|\b429\b|overloaded|\b529\b",
    re.I,
)
AUTH = re.compile(
    r"\b401\b|\b403\b|authentication|token has expired|token_expired|revoked|"
    r"invalid (?:api key|bearer|oauth|token)|CLAUDE_CODE_OAUTH_TOKEN is required",
    re.I,
)
EPOCH = re.compile(r"\|(\d{10})\b")
# Claude Code's own subscription-limit results. Specific enough to trust even
# inside the long JSON result lines that error_lines() filters out.
# Claude Code's own OAuth failures; like the limit messages, they arrive inside
# long JSON result lines that error_lines() filters out.
SUBSCRIPTION_AUTH = re.compile(
    r"OAuth (?:access )?token has expired|Re-authenticate to continue|"
    r"OAuth token (?:has been )?revoked",
    re.I,
)
SUBSCRIPTION_LIMIT = re.compile(
    r"you'?ve hit your (?:\w+ )?limit|hit your session limit|usage limit reached", re.I
)
CLOCK = re.compile(r"resets (\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*\(([^)]+)\)", re.I)
ISO = re.compile(r"resets[^0-9]{0,20}(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)\s*(UTC)?")
BACKOFF = (600, 1200, 1800)
AUTH_WAIT = 600
OTHER_RETRIES = 2

lock = threading.Lock()
pause_until = 0.0


def log(message: str) -> None:
    """Print one timestamped status line."""
    with lock:
        print(f"{datetime.now():%H:%M:%S} {message}", flush=True)


def token() -> str | None:
    """Return the freshest available subscription token."""
    bench = Path.home() / ".acco-bench-token"
    if bench.is_file() and bench.read_text(encoding="utf-8").strip():
        return bench.read_text(encoding="utf-8").strip()
    creds = Path.home() / ".claude" / ".credentials.json"
    if creds.is_file():
        oauth = json.loads(creds.read_text(encoding="utf-8")).get("claudeAiOauth", {})
        return oauth.get("accessToken") or None
    return None


def reset_time(text: str) -> float | None:
    """Return the limit reset as an epoch, when the error message states one."""
    if match := EPOCH.search(text):
        return float(match.group(1))
    if match := ISO.search(text):
        stamp = datetime.fromisoformat(match.group(1).replace(" ", "T"))
        return stamp.replace(tzinfo=timezone.utc).timestamp()
    if match := CLOCK.search(text):
        hour, minute, meridiem, zone = match.groups()
        hour = int(hour) % 12 + (12 if meridiem.lower() == "pm" else 0)
        try:
            tz = timezone.utc if zone.upper() == "UTC" else ZoneInfo(zone)
        except (KeyError, ValueError):
            return None
        now = datetime.now(tz)
        reset = now.replace(hour=hour, minute=int(minute or 0), second=0, microsecond=0)
        if reset <= now:
            reset += timedelta(days=1)
        return reset.timestamp()
    return None


def error_lines(text: str) -> str:
    """Return only short diagnostic lines; long lines are agent JSON/prose."""
    return "\n".join(
        line for line in text.splitlines()
        if len(line) < 400 and re.search(r"error|fail|limit|denied|expired|\b4\d\d\b", line, re.I)
    )


def classify(text: str) -> str:
    """Classify a failed attempt from its log."""
    if SUBSCRIPTION_AUTH.search(text):
        return "auth"
    if SUBSCRIPTION_LIMIT.search(text):
        return "limit"
    text = error_lines(text)
    if AUTH.search(text):
        return "auth"
    if LIMIT.search(text):
        return "limit"
    return "other"


def recorded(out: Path) -> int:
    """Return how many runs the task's result file already holds."""
    try:
        return len(json.loads(out.read_text(encoding="utf-8"))["runs"])
    except (OSError, ValueError, KeyError):
        return 0


def wait_while_paused(stop: Path) -> None:
    """Block while a shared limit pause is active."""
    while not stop.exists():
        remaining = pause_until - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 30))


def run_task(task: str, suite: Path, outdir: Path, expected: int) -> str:
    """Drive one task to completion through limits and token expiry."""
    global pause_until
    out = outdir / f"{task}-runs.json"
    stop = outdir / "STOP"
    limit_hits = other_failures = attempt = 0
    while True:
        wait_while_paused(stop)
        if stop.exists():
            return "stopped"
        current = token()
        if not current:
            log(f"NEEDS_TOKEN {task}: no token; create ~/.acco-bench-token")
            time.sleep(AUTH_WAIT)
            continue
        attempt += 1
        attempt_log = outdir / f"{task}.attempt-{attempt}.log"
        env = os.environ | {
            "CLAUDE_CODE_OAUTH_TOKEN": current,
            "PATH": f"{ROOT / '.venv' / 'bin'}:{os.environ['PATH']}",
        }
        before = recorded(out)
        with attempt_log.open("w", encoding="utf-8") as handle:
            rc = subprocess.run(
                [
                    "acco", "experiment", str(suite), "--allow-development",
                    "--task", task, "--out", str(out),
                ],
                cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT,
                check=False,
            ).returncode
        done = recorded(out)
        if rc == 0:
            log(f"done   {task} ({done}/{expected} runs)")
            return "done"
        if done > before:
            # Progress resets the per-kind failure budgets.
            limit_hits = other_failures = 0
        kind = classify(attempt_log.read_text(encoding="utf-8", errors="replace")[-20000:])
        if kind == "limit":
            text = attempt_log.read_text(encoding="utf-8", errors="replace")[-20000:]
            until = reset_time(text)
            wait = BACKOFF[min(limit_hits, len(BACKOFF) - 1)]
            target = (until + 60) if until and until > time.time() else time.time() + wait
            limit_hits += 1
            with lock:
                pause_until = max(pause_until, target)
            log(
                f"LIMIT  {task} ({done}/{expected}); all workers paused until "
                f"{datetime.fromtimestamp(pause_until):%H:%M}"
            )
        elif kind == "auth":
            log(f"NEEDS_TOKEN {task} ({done}/{expected}): auth failed; retry in "
                f"{AUTH_WAIT // 60} min (refresh the login or ~/.acco-bench-token)")
            time.sleep(AUTH_WAIT)
        else:
            other_failures += 1
            tail = attempt_log.read_text(encoding="utf-8", errors="replace")[-300:]
            log(f"ERROR  {task} ({done}/{expected}) attempt {attempt}: "
                + " ".join(tail.split())[-200:])
            if other_failures > OTHER_RETRIES:
                log(f"FAILED {task}: giving up after {other_failures} errors")
                return "failed"


def main() -> None:
    """Run every task in the suite with a small worker pool."""
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", type=Path)
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--task", action="append", dest="tasks")
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    tasks = args.tasks or [task["id"] for task in suite["tasks"]]
    expected = 2 * int(suite["design"]["trials_per_task"])
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "STOP").unlink(missing_ok=True)
    (args.outdir / "runner.pid").write_text(str(os.getpgrp()), encoding="utf-8")
    log(f"start  {len(tasks)} tasks x {expected} runs, {args.jobs} workers")

    queue = list(tasks)
    results: dict[str, str] = {}

    def worker() -> None:
        while True:
            with lock:
                if not queue:
                    return
                task = queue.pop(0)
            results[task] = run_task(task, args.suite, args.outdir, expected)

    threads = [threading.Thread(target=worker) for _ in range(args.jobs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    summary = {kind: sum(v == kind for v in results.values()) for kind in set(results.values())}
    log(f"ALL_FINISHED {summary}")


if __name__ == "__main__":
    main()
