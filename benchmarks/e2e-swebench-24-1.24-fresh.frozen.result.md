# Fresh frozen SWE-bench result: ACCO 1.24.0 vs plain Claude Code

**Status: fresh frozen evidence; the headline is withheld.** The protocol is
valid (`protocol_valid: true`, no issues), but ACCO solved fewer tasks than
plain Claude Code (52/72 vs 55/72). The gate requires treatment success ≥
baseline success, so `acco benchmark` reports no cost-per-success figure
(`claim_allowed: false`). The frozen 1.22.1 result remains the current
publishable cost-per-success evidence. Aggregates:
[`e2e-swebench-24-1.24-fresh.frozen.summary.json`](e2e-swebench-24-1.24-fresh.frozen.summary.json).

## Protocol

This follows [`e2e-1.24-evidence-plan.md`](e2e-1.24-evidence-plan.md), lane B
(fresh headline cohort).

| | |
|---|---|
| Suite | [`e2e-swebench-24-1.24-fresh.frozen.json`](e2e-swebench-24-1.24-fresh.frozen.json), committed (`b068fd2`) before the first paid run (`task_definition_sha256` `7770010c…5037`, `frozen_at` 2026-09-30T10:36Z) |
| Cohort | 24 SWE-bench Verified tasks never used by the 1.22.1 cohort or the 2026-09-27 development study; 6 repositories (astropy, matplotlib, pylint, pytest, scikit-learn, xarray) |
| Selection | [`scripts/build_e2e_124_fresh_candidate.py`](../scripts/build_e2e_124_fresh_candidate.py): pytest-graded repositories, the 1.22.1 difficulty bands, task-export known-bad instances excluded, per-repository shuffle (seed 20260930), round-robin draw. Every gold patch was checked to resolve in its official image before freezing; none was rejected. No task was substituted after any agent run |
| Design | 3 paired trials per task, randomized arm order (seed 20260930): 144 runs |
| Agent | Claude Code 2.1.276, `claude-sonnet-5`, Claude subscription |
| Environment | Each run inside the task's official SWE-bench image; the history-isolated snapshot is mounted at `/testbed` |
| Arms | **Claude Code**: plain, `ACCO_DISABLED=1`. **ACCO**: 1.24.0 (`6c1689d`), default `acco setup --host claude`, run-scoped `ACCO_STATE_DIR`; provider proxy and output holdout not enabled |
| Grading | Hidden tests in the official image after the agent finishes; agent edits to test files are stripped |
| Cost | Transcript usage × `claude-sonnet-5-rates-2026-09-19.json` (cache-TTL aware); equivalent API cost, not the subscription bill |
| Run window | 2026-09-30 10:36 to 20:44 UTC, paused twice for subscription usage limits by `scripts/run_resilient_experiment.py`; no manual intervention, no failed tasks |

## Result

| | Claude Code | ACCO 1.24.0 |
|---|---:|---:|
| Solved | **55/72** | **52/72** |
| Total cost | $23.54 | $18.94 (−19.5%) |
| Cost per solved task | $0.428 | $0.364 (−14.9%, not a claim: gate withheld) |
| Total tokens | 60.5M | 46.3M (−23.6%) |
| Output tokens | 540k | 447k (−17.1%) |
| Model calls | 1,444 | 1,173 (−18.8%) |

Task-cluster bootstrap, 95% (2,000 resamples over the 24 tasks):

| Metric | Interval |
|---|---|
| Cost reduction | 5.4% to 31.1% |
| Token reduction | 7.5% to 36.3% |
| Cost-per-success reduction | −0.8% to 26.9% (includes zero) |
| Success-rate change | −9.7 to +1.4 points |

Paired outcomes: 49 trials solved by both arms, 3 only by ACCO
(astropy-13236, matplotlib-23299, pytest-7205), and 6 only by plain Claude
Code (astropy-13977, astropy-14182, matplotlib-23299, matplotlib-24570,
pytest-5840, pytest-7205). ACCO was cheaper on 17 of 24 tasks.

### Per task (3 trials per arm)

| Task | CC solved | CC $ | ACCO solved | ACCO $ | Cost change | Recovery v2 active |
|---|---|---:|---|---:|---:|---|
| astropy-12907 | 3/3 | 0.43 | 3/3 | 0.38 | −12% | 0/3 |
| astropy-13236 | 2/3 | 1.58 | 3/3 | 1.28 | −19% | 3/3 |
| astropy-13453 | 3/3 | 0.86 | 3/3 | 0.64 | −26% | 2/3 |
| astropy-13977 | 1/3 | 1.62 | 0/3 | 1.39 | −14% | 0/3 |
| astropy-14182 | 3/3 | 1.24 | 2/3 | 0.81 | −35% | 1/3 |
| matplotlib-22865 | 3/3 | 1.13 | 3/3 | 0.50 | −56% | 2/3 |
| matplotlib-23299 | 1/3 | 1.36 | 1/3 | 1.90 | +40% | 3/3 |
| matplotlib-23476 | 0/3 | 1.37 | 0/3 | 1.13 | −17% | 1/3 |
| matplotlib-24570 | 3/3 | 0.50 | 2/3 | 0.45 | −9% | 1/3 |
| matplotlib-24970 | 3/3 | 0.71 | 3/3 | 0.67 | −5% | 1/3 |
| xarray-3305 | 3/3 | 0.79 | 3/3 | 0.81 | +2% | 2/3 |
| xarray-4075 | 3/3 | 0.36 | 3/3 | 0.33 | −7% | 0/3 |
| xarray-4687 | 3/3 | 2.29 | 3/3 | 1.14 | −50% | 3/3 |
| xarray-6938 | 0/3 | 1.18 | 0/3 | 1.26 | +7% | 3/3 |
| pylint-4604 | 0/3 | 0.89 | 0/3 | 0.65 | −27% | 0/3 |
| pylint-6903 | 3/3 | 0.48 | 3/3 | 0.59 | +22% | 1/3 |
| pytest-10051 | 3/3 | 0.56 | 3/3 | 0.41 | −25% | 0/3 |
| pytest-10081 | 3/3 | 1.06 | 3/3 | 0.69 | −35% | 2/3 |
| pytest-5840 | 1/3 | 2.54 | 0/3 | 1.22 | −52% | 1/3 |
| pytest-7205 | 2/3 | 0.83 | 2/3 | 0.90 | +9% | 2/3 |
| sklearn-12973 | 3/3 | 0.29 | 3/3 | 0.33 | +16% | 0/3 |
| sklearn-13142 | 3/3 | 0.29 | 3/3 | 0.28 | −2% | 0/3 |
| sklearn-14087 | 3/3 | 0.86 | 3/3 | 0.81 | −6% | 0/3 |
| sklearn-25931 | 3/3 | 0.33 | 3/3 | 0.36 | +11% | 0/3 |

## 1.24 runtime activation

Every ACCO run recorded activation evidence (72/72, no collection errors).

| Surface | ACCO runs activated |
|---|---:|
| `task_contract` | 72/72 |
| `recovery_v2` | 28/72 |
| `tool_field_learning` | 0/72 |
| `cache_ttl_learning` | 0/72 |
| `output_holdout` (not enabled) | 0/72 |
| `provider_observability` (proxy not enabled) | 0/72 |
| `out_of_context_execution` | 0/72 |
| `session_continuity` | 0/72 |

Agents made no `mcp__acco__*` calls; efficiency events were 59 savings and 13
waste. A surface at zero is not covered by this experiment. Activation does
not establish benefit, and there was no ablation, so none of the cost
reduction is attributed to a specific 1.24 feature.

## Reading the result

- **Claim ladder** (from the evidence plan): activation observed, and a
  context/token and cost reduction measured with intervals that exclude zero.
  **Success parity was not established**, so the ladder stops there: no
  cost-per-success claim for 1.24.
- **Success:** the −3 net trials fall on astropy-13977, astropy-14182,
  matplotlib-24570 and pytest-5840 (one trial each, against one gained on
  astropy-13236). The success-rate interval (−9.7 to +1.4 points) includes
  zero, so this does not show a regression either. The sample cannot tell a
  real 4-point drop from noise.
- **Where it saves:** long, iterative tasks such as matplotlib-22865,
  pytest-5840 and xarray-4687 (−50% to −56%). Small tasks move within about
  ±20%. The one large increase is matplotlib-23299 (+40%), solved 1/3 by
  each arm.
- **Quality:** only hidden-test pass/fail was measured. The blind
  output-quality grader was not run.

## Relation to the 1.22.1 result

The frozen [1.22.1 result](e2e-swebench-24-subscription.frozen.result.md)
(58/72 vs 58/72, −26.2% cost per success) stays as historical, publishable
evidence for that cohort. This run uses different, unseen tasks, a different
ACCO version and a different baseline success rate, so the two figures are not
directly comparable. Per the protocol, this cohort is now spent: it must not be
tuned against or re-run until it passes.

## Reproducing

```bash
docker build -f benchmarks/e2e-agent.Dockerfile --build-arg CLAUDE_CODE_VERSION=2.1.276 \
  -t acco-e2e-agent:2.1.276-acco-6c1689d .          # at commit 6c1689d
python scripts/prepare_e2e_repos.py benchmarks/e2e-swebench-24-1.24-fresh.frozen.json
python scripts/run_resilient_experiment.py \
  benchmarks/e2e-swebench-24-1.24-fresh.frozen.json results/ --jobs 3
python scripts/merge_e2e_results.py benchmarks/e2e-swebench-24-1.24-fresh.frozen.json \
  merged-runs.json results/*-runs.json
acco benchmark merged-runs.json --rates benchmarks/claude-sonnet-5-rates-2026-09-19.json \
  --require-publishable
```

The cohort can be rebuilt from SWE-bench Verified with
`python scripts/build_e2e_124_fresh_candidate.py OUT.json --validate`.
