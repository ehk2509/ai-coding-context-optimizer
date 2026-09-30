#!/usr/bin/env python3
"""Build the unseen ACCO 1.24 fresh-cohort candidate from SWE-bench Verified.

Selection is mechanical and seeded so it can be reproduced and cannot be tuned
against agent outcomes:

1. start from every SWE-bench Verified instance;
2. keep repositories whose official harness command is ``pytest -rA`` (the
   grader parses ``-rA`` status lines), and the difficulty bands used by the
   published 1.22.1 cohort (``<15 min fix`` and ``15 min - 1 hour``);
3. drop every task of the published cohort / 2026-09-27 development study and
   every instance listed as known-bad by the task export;
4. shuffle each repository's pool with ``--seed`` and draw round-robin across
   repositories (sorted by name) until ``--tasks`` are selected;
5. with ``--validate``, run the gold patch through the same Docker grader the
   experiment uses; a task whose gold patch does not resolve is replaced by the
   next task of the same repository's seeded order. No agent is involved.

Prompts are built exactly as in the published cohort. The output is a
candidate: freeze it with ``prepare_e2e_124_evidence.py fresh`` and commit the
frozen manifest before the first paid run.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import re
import sys
import tempfile
import urllib.request

ROWS_URL = (
    "https://datasets-server.huggingface.co/rows?dataset=princeton-nlp/"
    "SWE-bench_Verified&config=default&split=test&offset={offset}&length=100"
)
TASK_EXPORT = "https://github.com/kimjune01/swebench-verified"
REFERENCE = Path("benchmarks/e2e-swebench-24-subscription.frozen.json")

# Repository id -> (SWE-bench repo, clone URL, extra pytest flags).
REPOSITORIES = {
    "astropy": ("astropy/astropy", "https://github.com/astropy/astropy.git", ""),
    "matplotlib": (
        "matplotlib/matplotlib",
        "https://github.com/matplotlib/matplotlib.git",
        "",
    ),
    "pylint": ("pylint-dev/pylint", "https://github.com/pylint-dev/pylint.git", ""),
    "pytest": ("pytest-dev/pytest", "https://github.com/pytest-dev/pytest.git", ""),
    "requests": ("psf/requests", "https://github.com/psf/requests.git", ""),
    "scikit-learn": (
        "scikit-learn/scikit-learn",
        "https://github.com/scikit-learn/scikit-learn.git",
        "",
    ),
    "seaborn": ("mwaskom/seaborn", "https://github.com/mwaskom/seaborn.git", "--no-header "),
    "xarray": ("pydata/xarray", "https://github.com/pydata/xarray.git", ""),
}
DIFFICULTIES = {"<15 min fix", "15 min - 1 hour"}

# KNOWN_BAD.md of the task export (gold patch fails, flaky, external services,
# weak tests).
KNOWN_BAD = {
    "astropy__astropy-7606", "astropy__astropy-7166", "astropy__astropy-7336",
    "astropy__astropy-7671", "astropy__astropy-8707", "astropy__astropy-8872",
    "matplotlib__matplotlib-20488", "matplotlib__matplotlib-23987",
    "pylint-dev__pylint-6528", "pylint-dev__pylint-7080", "pylint-dev__pylint-7277",
    "psf__requests-1963", "psf__requests-2317", "psf__requests-2674",
    "psf__requests-1724", "psf__requests-1766", "psf__requests-1921",
    "mwaskom__seaborn-3010",
}

PROMPT_HEADER = (
    "Solve the historical software issue below in the checked-out repository.\n"
    "Implement a high-quality, general-purpose fix. Keep the change minimal and focused.\n"
    "Do not inspect remote resources, hidden grader files, or Git history outside the current snapshot.\n"
    "Do not hard-code for a specific test case and do not modify tests merely to force a pass.\n"
    "You may inspect and edit the repository and run any locally available checks.\n"
    "Leave the final code changes in the working tree; do not commit them.\n"
    "\n"
    "--- HISTORICAL ISSUE ---\n"
)


def _fetch_rows(cache: Path | None) -> list[dict]:
    if cache and cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for offset in range(0, 500, 100):
        with urllib.request.urlopen(ROWS_URL.format(offset=offset), timeout=60) as resp:
            rows.extend(item["row"] for item in json.load(resp)["rows"])
    if len(rows) != 500:
        raise SystemExit(f"expected 500 SWE-bench Verified rows, got {len(rows)}")
    if cache:
        cache.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def _prompt(problem: str) -> str:
    return PROMPT_HEADER + re.sub(r"<!--.*?-->", "", problem, flags=re.S).strip() + "\n"


def _test_files(test_patch: str) -> list[str]:
    files = re.findall(r"^diff --git a/(\S+) b/\S+", test_patch, flags=re.M)
    return list(dict.fromkeys(files))


def _task(row: dict, repo_id: str) -> dict:
    _, _, flags = REPOSITORIES[repo_id]
    prompt = _prompt(row["problem_statement"])
    instance = row["instance_id"]
    image_name = instance.replace("__", "_1776_")
    return {
        "id": instance,
        "repository": repo_id,
        "revision": row["base_commit"],
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "test_patch": row["test_patch"],
        "swebench": {
            "image": f"docker.io/swebench/sweb.eval.x86_64.{image_name}:latest",
            "env_activate": "source /opt/miniconda3/bin/activate testbed",
            "test_command": f"pytest {flags}-rA " + " ".join(_test_files(row["test_patch"])),
        },
        "verifier_timeout_seconds": 1800,
        "source": {
            "dataset": "SWE-bench Verified",
            "instance_id": instance,
            "task_export": TASK_EXPORT,
            "fixing_pr": (
                f"https://github.com/{row['repo']}/pull/{instance.rsplit('-', 1)[1]}"
            ),
            "original_problem_sha256": hashlib.sha256(
                row["problem_statement"].encode("utf-8")
            ).hexdigest(),
            "fail_to_pass": json.loads(row["FAIL_TO_PASS"]),
            "difficulty": row["difficulty"],
        },
    }


def _gold_resolves(task: dict, gold_patch: str, work: Path) -> tuple[bool, str]:
    from acco.experiment import _swebench_reference_passed
    from acco.swebench_docker import grade_swebench, passed_tests, verify_swebench

    work.mkdir(parents=True, exist_ok=True)
    timeout = int(task["verifier_timeout_seconds"])
    try:
        reference = _swebench_reference_passed(task, work / "reference", timeout=timeout)
    except ValueError as exc:
        return False, str(exc)
    (work / "gold.patch").write_text(gold_patch, encoding="utf-8")
    (work / "hidden-test.patch").write_text(task["test_patch"], encoding="utf-8")
    rc, _ = verify_swebench(
        image=task["swebench"]["image"],
        agent_patch=work / "gold.patch",
        test_patch=work / "hidden-test.patch",
        test_command=task["swebench"]["test_command"],
        env_activate=task["swebench"]["env_activate"],
        stdout_path=work / "gold.stdout",
        stderr_path=work / "gold.stderr",
        timeout=timeout,
    )
    grade = grade_swebench(
        task["source"]["fail_to_pass"],
        reference,
        passed_tests((work / "gold.stdout").read_text(encoding="utf-8", errors="replace")),
    )
    ok = bool(grade["resolved"]) and rc != 124
    return ok, "" if ok else f"gold patch not resolved (rc={rc}): {grade}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--tasks", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20260930)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    parser.add_argument("--rows-cache", type=Path, default=None)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--validation-dir", type=Path, default=None)
    args = parser.parse_args()

    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    used = {str(task["id"]) for task in reference["tasks"]}
    by_swebench_repo = {spec[0]: repo_id for repo_id, spec in REPOSITORIES.items()}

    pools: dict[str, list[dict]] = {repo_id: [] for repo_id in REPOSITORIES}
    for row in _fetch_rows(args.rows_cache):
        repo_id = by_swebench_repo.get(row["repo"])
        if (
            repo_id is None
            or row["instance_id"] in used
            or row["instance_id"] in KNOWN_BAD
            or row["difficulty"] not in DIFFICULTIES
        ):
            continue
        pools[repo_id].append(row)
    rng = random.Random(args.seed)
    for repo_id in sorted(pools):
        pools[repo_id].sort(key=lambda row: row["instance_id"])
        rng.shuffle(pools[repo_id])

    validation_dir = args.validation_dir or Path(tempfile.mkdtemp(prefix="acco-gold-"))
    selected: list[dict] = []
    rejected: list[dict] = []
    cursor = {repo_id: 0 for repo_id in pools}
    while len(selected) < args.tasks:
        progressed = False
        for repo_id in sorted(pools):
            if len(selected) >= args.tasks:
                break
            while cursor[repo_id] < len(pools[repo_id]):
                row = pools[repo_id][cursor[repo_id]]
                cursor[repo_id] += 1
                task = _task(row, repo_id)
                if args.validate:
                    ok, reason = _gold_resolves(
                        task, row["patch"], validation_dir / task["id"]
                    )
                    print(f"{task['id']}: {'ok' if ok else reason}", file=sys.stderr, flush=True)
                    if not ok:
                        rejected.append({"id": task["id"], "reason": reason[:500]})
                        continue
                selected.append(task)
                progressed = True
                break
        if not progressed:
            raise SystemExit(f"pool exhausted after {len(selected)} tasks")

    suite = {
        key: deepcopy(reference[key])
        for key in ("suite_version", "design", "runner", "quality_grader", "evidence")
    }
    suite["protocol"] = {"task_definitions_frozen": False}
    suite["repositories"] = {
        repo_id: {"url": REPOSITORIES[repo_id][1], "path": f"external-e2e/{repo_id}"}
        for repo_id in sorted({task["repository"] for task in selected})
    }
    suite["tasks"] = selected
    suite["cohort_selection"] = {
        "dataset": "princeton-nlp/SWE-bench_Verified (test split, 500 rows)",
        "repositories": sorted(REPOSITORIES),
        "difficulties": sorted(DIFFICULTIES),
        "excluded": "published 1.22.1 cohort / 2026-09-27 development study task ids "
        "and the task export's KNOWN_BAD.md",
        "seed": args.seed,
        "method": "per-repository seeded shuffle, round-robin across repositories "
        "sorted by name",
        "gold_patch_validated": bool(args.validate),
        "rejected_by_gold_validation": rejected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} with {len(selected)} tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
