# Frozen paired SWE-bench result: ACCO 1.22.1 vs plain Claude Code

**Status: frozen paired evidence. It passes the `acco benchmark` publication
gate (`protocol_valid: true`, no issues).** Scope: one model (`claude-sonnet-5`),
one 24-task SWE-bench Verified suite, ACCO commit `19f17e5` (1.22.1), and
equivalent API cost. It is not a universal savings figure. Aggregates:
[`e2e-swebench-24-subscription.frozen.summary.json`](e2e-swebench-24-subscription.frozen.summary.json).

## Protocol

| | |
|---|---|
| Suite | [`e2e-swebench-24-subscription.frozen.json`](e2e-swebench-24-subscription.frozen.json), frozen and pushed before any run (`task_definition_sha256` `735af6a2…e888`, `frozen_at` 2026-09-28T12:00+02:00) |
| Tasks | 24 SWE-bench Verified tasks (scikit-learn, pytest, astropy, pylint, requests, xarray, seaborn) |
| Design | 3 paired trials per task, randomized arm order (seed 20260928): 144 runs |
| Agent | Claude Code 2.1.276, `claude-sonnet-5`, Claude Pro subscription |
| Environment | Each run inside the task's official SWE-bench image; the history-isolated snapshot is mounted at `/testbed` |
| Arms | **Claude Code**: plain, `ACCO_DISABLED=1`. **ACCO**: `19f17e5` (1.22.1), default `acco setup --host claude`, including the verification-coverage rule and the task checklist; provider proxy not enabled |
| Grading | Hidden tests in the official image after the agent finishes; agent edits to test files are stripped |
| Cost | Transcript usage × `claude-sonnet-5-rates-2026-09-19.json` (cache-TTL aware); equivalent API cost, not the subscription bill |
| Run window | 2026-09-28 09:54 to 2026-09-29 04:49, paused three times for subscription usage limits by `scripts/run_resilient_experiment.py`; no manual intervention |

## Result

| | Claude Code | ACCO |
|---|---:|---:|
| Solved | 58/72 | **58/72** |
| Total cost | $31.39 | $23.18 |
| **Cost per solved task** | **$0.541** | **$0.400 (−26.2%)** |
| Total tokens | 77.6M | 57.3M (−26.1%) |
| Output tokens | 842k | 576k (−31.5%) |
| Model calls | 1,567 | 1,309 (−16.5%) |

Task-cluster bootstrap, 95% (2,000 resamples over the 24 tasks):

| Metric | Interval |
|---|---|
| **Cost-per-success reduction** | **12.3% to 37.1%** |
| Cost reduction | 13.7% to 35.0% |
| Token reduction | 13.0% to 35.7% |
| Success-rate change | −5.6 to +5.6 points |

Paired outcomes: 56 trials solved by both arms, 2 only by ACCO
(requests-6028, xarray-6599), and 2 only by plain Claude Code (seaborn-3069,
requests-5414). ACCO was cheaper on 16 of 24 tasks.

### Per task (3 trials per arm)

| Task | CC solved | CC $ | ACCO solved | ACCO $ | Cost change |
|---|---|---:|---|---:|---:|
| astropy-13033 | 0/3 | 0.52 | 0/3 | 0.96 | +84% |
| astropy-14096 | 3/3 | 0.81 | 3/3 | 0.71 | −12% |
| astropy-14309 | 3/3 | 0.28 | 3/3 | 0.34 | +22% |
| astropy-14598 | 0/3 | 2.79 | 0/3 | 1.31 | −53% |
| seaborn-3069 | 3/3 | 3.36 | 2/3 | 2.25 | −33% |
| seaborn-3187 | 3/3 | 2.40 | 3/3 | 1.70 | −29% |
| requests-1142 | 3/3 | 0.42 | 3/3 | 0.37 | −12% |
| requests-2931 | 3/3 | 0.98 | 3/3 | 0.99 | +1% |
| requests-5414 | 3/3 | 1.20 | 2/3 | 0.84 | −30% |
| requests-6028 | 2/3 | 3.43 | 3/3 | 1.54 | −55% |
| xarray-6461 | 3/3 | 0.60 | 3/3 | 0.68 | +14% |
| xarray-6599 | 2/3 | 4.99 | 3/3 | 3.79 | −24% |
| xarray-7393 | 3/3 | 0.65 | 3/3 | 0.69 | +5% |
| pylint-4661 | 0/3 | 1.16 | 0/3 | 1.14 | −2% |
| pylint-4970 | 0/3 | 2.78 | 0/3 | 1.85 | −34% |
| pylint-6386 | 3/3 | 1.80 | 3/3 | 1.22 | −32% |
| pytest-5262 | 3/3 | 0.33 | 3/3 | 0.27 | −20% |
| pytest-5809 | 3/3 | 0.31 | 3/3 | 0.27 | −13% |
| pytest-7324 | 3/3 | 1.06 | 3/3 | 0.77 | −27% |
| pytest-7521 | 3/3 | 0.48 | 3/3 | 0.42 | −14% |
| sklearn-12585 | 3/3 | 0.19 | 3/3 | 0.21 | +8% |
| sklearn-13439 | 3/3 | 0.20 | 3/3 | 0.23 | +14% |
| sklearn-14141 | 3/3 | 0.29 | 3/3 | 0.26 | −9% |
| sklearn-14496 | 3/3 | 0.34 | 3/3 | 0.38 | +11% |

## Reading the result

- **Mechanism:** fewer model calls and shorter generations. Every Claude Code
  call re-reads a fixed ~28k-token prefix, so avoided calls dominate the
  saving. Across all 72 ACCO transcripts agents made zero `mcp__acco__*`
  calls; the effect comes from the hooks and the injected policy. The task
  checklist fired in exactly 3 runs, all on seaborn-3187.
- **Where it saves:** long, iterative tasks such as requests-6028,
  astropy-14598, pylint-4970 and seaborn-3069 (−33% to −55%). Small tasks that
  take 5–10 calls move within about ±15%, which is noise.
- **Where it costs more:** astropy-13033 (+84%), a task both arms fail every
  time; ACCO's failing attempts ran longer.
- **Quality:** success parity is measured by independent hidden tests. The
  project's blind output-quality grader was **not** run, so no claim is made
  about the quality of responses beyond test pass/fail.

## What changed from the earlier unfrozen study

The [144-run development study](e2e-subscription-swebench-24-2026-09-27.md)
(ACCO `4856959`) measured −21.1% but solved 55/72 vs 56/72, so the gate
withheld its headline. ACCO lost trials on multi-path issues:
`seaborn-3187` 1/3, where agents fixed the first named path and stopped.
Between the two runs, #148 added a verification-coverage rule and a
prompt-derived task checklist; an ablation removed a checklist variant that
hurt `pylint-6386` (2/5 vs 4/5). In this frozen run, seaborn-3187 is 3/3 and
pylint-6386 is 3/3, and success is at parity.

## Not covered

- Features added after `19f17e5` (the 1.23.0 native host hooks and
  out-of-context execution) are not measured here.
- One model (Sonnet 5), one host (Claude Code 2.1.276), one task suite.
  Everyday workloads, other models and other hosts may differ.
- Blind output-quality grading was not run.

## Reproducing

```bash
docker build -f benchmarks/e2e-agent.Dockerfile --build-arg CLAUDE_CODE_VERSION=2.1.276 \
  -t acco-e2e-agent:2.1.276-acco-19f17e5 .          # at commit 19f17e5
python scripts/run_resilient_experiment.py \
  benchmarks/e2e-swebench-24-subscription.frozen.json results/ --jobs 3
# merge results/*-runs.json into one file, then:
acco benchmark merged-runs.json --rates benchmarks/claude-sonnet-5-rates-2026-09-19.json
```

Runs need a Claude subscription token (`claude setup-token`, saved to
`~/.acco-bench-token`) and the task repositories cloned under
`benchmarks/external-e2e/`.
