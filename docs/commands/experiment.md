# `acco experiment`

Run or dry-run randomized paired agent experiments.

## Synopsis

```bash
acco experiment <suite> [--out FILE] [--dry-run] [--allow-development] [--allow-user-hook] [--task ID ...] [--print-task-definition-hash]
```

## Arguments and options

- `suite` required.
- `--out` default `benchmark-runs.json`.
- `--dry-run` validates/prints schedule without model calls.
- `--allow-development` permits unfrozen/narrow suites.
- `--allow-user-hook` permits possible double instrumentation.
- `--task` repeatable task filter.
- `--print-task-definition-hash` prints the freeze hash.

A production evidence suite may also declare `quality_grader` (judge command,
judge identity, assignment seed, timeout) and `evidence.pricing_file`. Those
fields are carried into run checkpoints for `blind-grade` / `evidence-run`
but do not alter the already-frozen task-definition hash.

For routing experiments, `runner.condition_profiles.baseline.model` and
`runner.condition_profiles.enabled.model` may override `runner.model` per
arm. Use the same `install_acco` and `env` values in both arms so model
choice is the only treatment. Each completed run records `actual_models` from
transcript usage; `model-route-calibrate` requires exactly one actual model and
requires it to match the declared arm model.

## Exit codes

`0` success; `2` invalid suite/harness configuration.

## Output contract

JSON result/checkpoint; see [Machine-readable contracts](../JSON_OUTPUTS.md#experiment-always-json).

Each completed run embeds transcript-measured fresh input, cache creation
(total plus 5-minute, 1-hour, and unknown-TTL buckets), cache read, output
tokens, model-call count, and tool-call count. Enabled runs isolate ACCO state
under that run's artifact directory and, when the host executes the managed
hooks, also embed output task/mode/budget telemetry plus a
telemetry-vs-transcript usage-integrity check.

Enabled runs additionally capture a content-free `runtime_activation` record
before their temporary worktree is destroyed. It reports event-kind counts,
ACCO tool calls, Recovery v2 statistics, learned-field/cache-TTL evidence, and
provider/framework observability. These counters prove only that a mechanism
was exercised; task success and cost effects still come from the paired
end-to-end evaluation.

## Authoritative runtime help

Run `acco experiment --help` for argparse's exact usage text for the installed version.
