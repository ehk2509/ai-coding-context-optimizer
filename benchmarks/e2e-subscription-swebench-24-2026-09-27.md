# Paired SWE-bench run on a Claude subscription (144 runs, 2026-09-25/27)

> **Superseded** by the frozen, gate-valid re-run:
> [`e2e-swebench-24-subscription.frozen.result.md`](e2e-swebench-24-subscription.frozen.result.md)
> (ACCO 1.22.1, 58/72 vs 58/72, −26.2% cost per success).

**Status: development evidence, not a publishable savings claim.** The task
definitions were adapted for local subscription runs (repository paths, runner
command, task-image execution), so the suite is not frozen, and ACCO solved one
run fewer than plain Claude Code, so `acco benchmark` withholds the headline
figure. Machine-readable aggregates:
[`e2e-subscription-swebench-24-2026-09-27.summary.json`](e2e-subscription-swebench-24-2026-09-27.summary.json).

## Question

Does ACCO, as installed by `acco setup --host claude`, lower dollars per
independently verified successful coding task compared with plain Claude Code?

## Setup

| | |
|---|---|
| Tasks | The 24 SWE-bench Verified tasks of `e2e-swebench-24.frozen.json` (scikit-learn, pytest, astropy, pylint, requests, xarray, seaborn) |
| Design | 3 paired trials per task, randomized arm order: 144 runs |
| Agent | Claude Code 2.1.276, `claude-sonnet-5`, Claude Pro subscription (`acco.claude_docker --auth subscription`) |
| Environment | Each run inside the task's official SWE-bench image (`--task-image`): the snapshot is mounted at `/testbed` with the image's environment commit as base and its build products excluded, so the agent can run the same tests as the grader |
| Arms | **Claude Code**: plain, `ACCO_DISABLED=1`. **ACCO**: commit `4856959` (#129), default `acco setup` (hooks, MCP server, skill, output policy); provider proxy not enabled |
| Grading | Hidden tests applied after the agent in the official image; agent edits to test files are stripped |
| Cost | Transcript usage × `claude-sonnet-5-rates-2026-09-19.json` (cache-TTL aware). This is equivalent API cost, not the subscription bill |
| Runner | `scripts/run_resilient_experiment.py`: resumable per task; paused twice for usage limits and resumed automatically |

## Result

| | Claude Code | ACCO |
|---|---:|---:|
| Solved | 56/72 | 55/72 |
| Total cost | $29.88 | $23.16 |
| **Cost per solved task** | **$0.534** | **$0.421 (−21.1%)** |
| Total tokens | 75.8M | 56.4M (−25.6%) |
| Output tokens | 777k | 623k (−19.7%) |
| Model calls | 1,583 | 1,261 (−20.3%) |

Task-cluster bootstrap, 95% (2,000 resamples over the 24 tasks):

| Metric | Interval |
|---|---|
| Cost-per-success reduction | 9.7% to 31.4% |
| Cost reduction | 15.0% to 29.6% |
| Token reduction | 18.0% to 32.5% |
| Success-rate change | −9.7 to +6.9 points |

ACCO was cheaper on 18 of 24 tasks. Paired outcomes: 51 trials solved by both
arms, 4 solved only by ACCO, 5 solved only by plain Claude Code.

### Per task (3 trials per arm)

| Task | CC solved | CC $ | ACCO solved | ACCO $ | Cost change |
|---|---|---:|---|---:|---:|
| astropy-13033 | 0/3 | 0.53 | 0/3 | 0.59 | +11% |
| astropy-14096 | 3/3 | 0.97 | 3/3 | 0.77 | −20% |
| astropy-14309 | 3/3 | 0.57 | 3/3 | 0.34 | −41% |
| astropy-14598 | 0/3 | 2.66 | 1/3 | 2.43 | −9% |
| seaborn-3069 | 2/3 | 2.90 | 3/3 | 2.31 | −20% |
| seaborn-3187 | 3/3 | 2.20 | 1/3 | 1.52 | −31% |
| requests-1142 | 3/3 | 0.41 | 3/3 | 0.42 | +2% |
| requests-2931 | 3/3 | 1.03 | 3/3 | 0.94 | −9% |
| requests-5414 | 2/3 | 1.16 | 2/3 | 0.95 | −18% |
| requests-6028 | 1/3 | 2.73 | 2/3 | 1.72 | −37% |
| xarray-6461 | 3/3 | 0.96 | 3/3 | 0.47 | −51% |
| xarray-6599 | 3/3 | 4.58 | 2/3 | 4.10 | −10% |
| xarray-7393 | 3/3 | 0.78 | 3/3 | 0.61 | −22% |
| pylint-4661 | 0/3 | 1.39 | 0/3 | 0.73 | −47% |
| pylint-4970 | 0/3 | 2.23 | 0/3 | 1.38 | −38% |
| pylint-6386 | 3/3 | 1.83 | 2/3 | 1.11 | −40% |
| pytest-5262 | 3/3 | 0.28 | 3/3 | 0.29 | +4% |
| pytest-5809 | 3/3 | 0.27 | 3/3 | 0.27 | +2% |
| pytest-7324 | 3/3 | 0.86 | 3/3 | 0.87 | +1% |
| pytest-7521 | 3/3 | 0.48 | 3/3 | 0.43 | −9% |
| sklearn-12585 | 3/3 | 0.21 | 3/3 | 0.20 | −5% |
| sklearn-13439 | 3/3 | 0.18 | 3/3 | 0.21 | +15% |
| sklearn-14141 | 3/3 | 0.30 | 3/3 | 0.22 | −26% |
| sklearn-14496 | 3/3 | 0.38 | 3/3 | 0.29 | −24% |

## Findings

1. **The saving comes from fewer model calls, not smaller calls.** Every
   Claude Code call re-reads a fixed ~28k-token prefix (system prompt and tool
   definitions); on the everyday tasks it was a median 84% of input tokens.
   ACCO's focused-first verification wording (#129) (start with the smallest
   test covering touched code, don't rerun unchanged failing commands) cut
   calls by 20%, and cost followed. Small, easy tasks (pytest, several
   scikit-learn) moved within ±15%, which is noise.
2. **Verification must stay mandatory.** An earlier policy ("Stop once the
   acceptance criteria are satisfied" under an unscoped output budget) showed
   ~50% "savings" that came from agents quitting before running tests;
   `psf__requests-2931` then failed 3/4 runs versus 0/4 for plain Claude Code.
   Fixed in #128. With narrow-first verification (#129) that task stayed 3/3.
3. **Focused verification can miss the second path an issue names.** On
   `seaborn-3187` the issue shows the bug through `seaborn.objects` and says it
   "also reproduces … using `scatterplot`". The failing ACCO runs fixed
   `_core/scales.py`, verified it, and stopped without touching the
   `scatterplot` path (`utils.py`). No existing test covers it, so running more
   tests would not have caught it. Two more of ACCO's five lost trials are on
   `pylint-6386` and `xarray-6599`, whose issues also point at a second
   symptom or API; that cause is not yet confirmed per transcript. Follow-up:
   an explicit coverage rule and a prompt-derived task checklist (#148).
4. **Four tasks are hard for both arms** (astropy-13033, astropy-14598,
   pylint-4661, pylint-4970: 0–1/3 each). ACCO still spent less on them.
5. **ACCO's retrieval MCP tools were not used.** Across all 72 ACCO
   transcripts agents made zero `mcp__acco__*` calls; the effect is carried
   entirely by hooks and the injected policy.

## Harness defects found and fixed along the way

Earlier runs of this benchmark were not trustworthy until these were fixed
(#128 and #148):

- Agents ran with Python 3.11 and no project dependencies, so old repositories
  could not import and tests could not run. Fixed by running inside the task
  image.
- History-isolated snapshots dropped tracked files that match `.gitignore`
  (scikit-learn's generated C sources) and kept `export-subst` rewrites, so the
  snapshot tree differed from the revision and agent edits to those files would
  silently leave the graded patch. Snapshots now equal the revision tree
  (verified for all 24 tasks).
- Claude Code refuses `--dangerously-skip-permissions` as root; the runner sets
  `IS_SANDBOX=1` for root hosts.
- Subscription usage limits and expired OAuth tokens arrive inside long JSON
  result lines; the resilient runner now recognizes both and waits instead of
  abandoning tasks.

## Earlier comparisons on subsets (same harness)

| ACCO version | Tasks × trials | Cost per success vs Claude Code |
|---|---|---|
| 1.17 unedited | 3 × 2 | −26%, but 4/6 vs 6/6 solved (skipped verification) |
| 1.17 + verification fix (#128) | 6 × 4 | −0.7% |
| `main` 4856959 (#129) | 6 × 2 | −20.1% |
| `main` 4856959 (#129) | **24 × 3** | **−21.1%**, 55 vs 56 solved |
| 1.17 + fix, log-heavy stress fixture | 1 × 10 | −24.5% (trial bootstrap 7–38%) |

## Reproducing

```bash
# 1. agent image from the commit under test
docker build -f benchmarks/e2e-agent.Dockerfile --build-arg CLAUDE_CODE_VERSION=2.1.276 \
  -t acco-e2e-agent:2.1.276-<tag> .
# 2. suite: e2e-swebench-24.frozen.json with local repository paths, the runner command
#    extended by `--auth subscription --task-image {task_image}`, and the enabled
#    profile {"install_acco": true, "instrumentation": "setup"}
# 3. run (resumable; survives usage limits and token expiry)
python scripts/run_resilient_experiment.py suite.json results/ --jobs 3
# 4. merge the per-task *-runs.json files and report
acco benchmark merged-runs.json --rates benchmarks/claude-sonnet-5-rates-2026-09-19.json
```

A long-lived `claude setup-token` token in `~/.acco-bench-token` avoids pauses
when the interactive login's access token expires.
